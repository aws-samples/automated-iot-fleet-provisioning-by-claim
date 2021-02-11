import json
import boto3
from datetime import date, datetime
import json
from urllib.request import urlopen
from zipfile import ZipFile, ZIP_DEFLATED
import io
from io import BytesIO
import os

iotClient = boto3.client('iot')
endpoint = boto3.client('iot-data')
s3Client = boto3.client('s3')

resourceTag = os.environ['ResourceTag']
region = os.environ['Region']

bootstrapPolicyName = '{}_birth_policy'.format(resourceTag)
BUCKET_NAME = '{}-per-vendor-bootstraps'.format(resourceTag)
rootCertUrl = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
rootCert = urlopen(rootCertUrl)

s3Client.create_bucket(Bucket=BUCKET_NAME, CreateBucketConfiguration={'LocationConstraint': region})

def handler(event, context):
    
    response = createModelBootstraps(event["models"])

    return {
        'statusCode': 200,
        'body': {'models_added' : json.dumps(response)}
    }

    
def createModelBootstraps(model_list):

    added_models = []
    
    for model in model_list:
        items = s3Client.list_objects_v2(
            Bucket=BUCKET_NAME,
            Prefix=model
        )
        
        if items["KeyCount"] == 0:
            certificates = iotClient.create_keys_and_certificate(setAsActive=True)
            iotClient.attach_policy(policyName=bootstrapPolicyName,target=certificates['certificateArn'])
            mem_zip = BytesIO()
            added_models.append(model)
            with ZipFile(mem_zip, mode="w", compression=ZIP_DEFLATED) as archive:
                archive.writestr('bootstrap-certificate.pem.crt', certificates['certificatePem'])
                archive.writestr('bootstrap-private.pem.key', certificates['keyPair']['PrivateKey'])
                archive.writestr('root.ca.pem', rootCert.read())
                archive.writestr('{}.txt'.format(certificates['certificateId']), "")
                
            mem_zip.seek(0)
            s3Client.upload_fileobj(mem_zip, BUCKET_NAME,'{0}/{0}_bootstraps.zip'.format(model))
    
    return added_models