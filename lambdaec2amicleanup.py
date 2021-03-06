# Automated AMI and Snapshot Deletion
# @Rajesh krishnamoorthy - modified the code to send notification email on cleanup
# This script will search for all instances having a tag with "Backup" or "backup"
# on it. As soon as we have the instances list, we loop through each instance
# and reference the AMIs of that instance. We check that the latest daily backup
# succeeded then we store every image that's reached its DeleteOn tag's date for
# deletion. We then loop through the AMIs, deregister them and remove all the
# snapshots associated with that AMI.

import boto3
import collections
import datetime
import time
import sys
import os

ec = boto3.client('ec2')
ec2 = boto3.resource('ec2')
images = ec2.images.filter(Owners=["self"])
aws_sns_arn = os.getenv('aws_sns_arn', None)

def send_to_sns(subject, message):
    if aws_sns_arn is None:
        return

    print "Sending notification to: %s" % aws_sns_arn

    client = boto3.client('sns')

    response = client.publish(
        TargetArn=aws_sns_arn,
        Message=message,
        Subject=subject)

    if 'MessageId' in response:
        print "Notification sent with message id: %s" % response['MessageId']
    else:
        print "Sending notification failed with response: %s" % str(response)



def lambda_handler(event, context):

    reservations = ec.describe_instances(
        Filters=[
            {'Name': 'tag-key', 'Values': ['backup', 'Backup']},
        ]
    ).get(
        'Reservations', []
    )

    instances = sum(
        [
            [i for i in r['Instances']]
            for r in reservations
        ], [])

    print "Found %d instances that need evaluated" % len(instances)

    to_tag = collections.defaultdict(list)

    date = datetime.datetime.now()
    date_fmt = date.strftime('%Y-%m-%d')

    imagesList = []

    backupSuccess = True

    for instance in instances:
	imagecount = 0

        for image in images:

               if image.name.startswith('Lambda - ' + instance['InstanceId']):

        
	        imagecount = imagecount + 1

                try:
                    if image.tags is not None:
                        deletion_date = [
                            t.get('Value') for t in image.tags
                            if t['Key'] == 'DeleteOn'][0]
                        delete_date = time.strptime(deletion_date, "%Y-%m-%d")
                except IndexError:
                    deletion_date = False
                    delete_date = False

                today_time = datetime.datetime.now().strftime('%Y-%m-%d')
                today_date = time.strptime(today_time, '%Y-%m-%d')

           
                if delete_date <= today_date:
                    imagesList.append(image.id)

                if image.name.endswith(date_fmt):
                    backupSuccess = True
                    print "Latest backup from " + date_fmt + " was a success"

        print "instance " + instance['InstanceId'] + " has " + str(imagecount) + " AMIs"

    print "============="

    print "About to process the following AMIs:"
    print imagesList

    if backupSuccess == True:

        myAccount = boto3.client('sts').get_caller_identity()['Account']

        snapshots = ec.describe_snapshots(MaxResults=1000, OwnerIds=[myAccount])['Snapshots']
        # loop through list of image IDs
        for image in imagesList:
            print "deregistering image %s" % image
            amiResponse = ec.deregister_image(
                DryRun=False,
                ImageId=image,
            )

            for snapshot in snapshots:
                if snapshot['Description'].find(image) > 0:
                    snap = ec.delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    print "Deleting snapshot " + snapshot['SnapshotId']
                    print "-------------"

    else:
        print "No current backup found. Termination suspended."
    message = "Hello,\n \nAmi cleanup has been initiated successfully for {} instances".format(imagesList)
    send_to_sns('EC2 AMI Cleanup', message)    
