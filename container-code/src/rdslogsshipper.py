#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and limitations under the License.
#
# Author: MADHURI PERI

import boto3, botocore
import os
from botocore.exceptions import ClientError


def getRDSInstances(region, rdsClient):
    dbInstancesList = []
    try:
        dbInstanceResp = rdsClient.describe_db_instances()
        for inst in dbInstanceResp['DBInstances']:
            print ("DB instance name {}".format(inst['DBName']))
            dbInstancesList.append(inst['DBName'])
    except  botocore.exceptions.ClientError as clienterror:
        errRespCode = int(clienterror.response['ResponseMetadata']['HTTPStatusCode'])
        if errRespCode == 404:
            print("There seem to be no rdsClient instances.")
        else:
            print ("ERROR - Unable to describe rdsClient instances" + clienterror.response['Error']['Message'])

    return dbInstancesList


def checkLastPointer(bucketName, logPointer):

    try:
        # Check in the s3 bucket for the dbinstance, if there are any files, and when was last file written
        lastDownloadDetails = s3Client.get_object(Bucket=bucketName, Key=logPointer)
        print ("lastDownloadDetails {}".format(lastDownloadDetails))

        # If this file exists, get the last downloaded details.
        # Read the S3 file.
        loggedTimeStamp = lastDownloadDetails['Body'].read(lastDownloadDetails['ContentLength'])

    except ClientError as KeyException:
        if KeyException.response['Error']['Code'] == 'NoSuchKey':
            print ("No s3 key found")
            print ("The DB Instance logs were never downloaded before!. Going to initiate download")
            loggedTimeStamp = 0
        else:
            raise KeyException

    return loggedTimeStamp


def downloadRDSLogs(region, s3Client, rdsClient, dbinst, logBucket):
    startDownload = False
    print ("Function download rds Logs into S3 bucket {} for database instance {}".format(logBucket, dbinst))

    logPointer = logBucket + '/' + dbinst + '/LOGPOINTER.TXT'

    loggedTimeStamp = checkLastPointer(logBucket, logPointer)
    print ("Logged timestamp {}".format(loggedTimeStamp))

    # Describe logs for instance
    dbLogFilesListResp = rdsClient.describe_db_log_files(
        DBInstanceIdentifier=dbinst
    )
    print (dbLogFilesListResp['DescribeDBLogFiles'])

    # Iterate over log files, and download each one IF not already downloaded.
    pointerTimeStamp = loggedTimeStamp
    for logFile in dbLogFilesListResp['DescribeDBLogFiles']:
        logFileName = logFile['LogFileName']

        LogFileData = ''
        if (loggedTimeStamp == 0) or (int(loggedTimeStamp) < logFile['LastWritten']):
            print ("Logfile {} had a last update logged at {}".format(logFile['LogFileName'], logFile['LastWritten']))
            marker = '0'
            LogFileData=downloadRDSLogPortion(region=region, rdsClient=rdsClient, dbinst=dbinst, logFileName=logFileName, marker=marker, LogFileData=LogFileData)
            pointerTimeStamp = logFile['LastWritten']
        else:
            print ("Logfile {} already downloaded....skipping".format(logFile['LogFileName']))

    # Write this logfile data to S3 bucket for future runs of this program
    writeToS3Bucket(region=region, s3Client=s3Client, bucketName=logBucket, fileNameKey=logPointer, data=pointerTimeStamp)


def downloadRDSLogPortion (region, rdsClient, dbinst, logFileName, marker, LogFileData):
    print ("Download RDS Log Portion for database instance {}, log file {}, marker {}".format(dbinst,logFileName, marker))

    dwnldLogFilePortionResp = rdsClient.download_db_log_file_portion(DBInstanceIdentifier=dbinst, LogFileName=logFileName, Marker=marker)
    print ("Response {}".format(dwnldLogFilePortionResp))
    marker = dwnldLogFilePortionResp['Marker']
    LogFileData = dwnldLogFilePortionResp['LogFileData']

    if dwnldLogFilePortionResp['AdditionalDataPending']:
        # More data exists, downlod the file again with new marker
        downloadRDSLogPortion(region=region, rdsClient=rdsClient, dbinst=dbinst, logFileName=logFileName, marker=marker, LogFileData=LogFileData)

    return LogFileData


def writeToS3Bucket(region, s3Client, bucketName, fileNameKey, data):
    print ("Will write logfile data to S3 bucket {}".format(bucketName))

    try:
        s3Client.put_object(Bucket=bucketName, Key=fileNameKey, Body=str(data))
    except ClientError as FileWriteError:
        print ("Error writing logdata to the bucket " + FileWriteError['Error']['Message'])

if __name__ == "__main__":

    region='us-west-2'
    rdsClient = boto3.client('rds', region_name=region)
    s3Client = boto3.client('s3', region_name=region)

    dbInstList = getRDSInstances(region, rdsClient)
    print ("RDS Database instances list {}".format(dbInstList))

    # Read this from environment variable.
    rdsLogsBucket = os.environ['RDSLOGSBUCKET']
    downloadRDSLogs(region=region, s3Client=s3Client, rdsClient=rdsClient, dbinst=dbInstList[0], logBucket=rdsLogsBucket)




