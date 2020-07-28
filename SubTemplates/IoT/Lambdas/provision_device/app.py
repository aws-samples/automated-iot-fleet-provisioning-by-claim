# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import cfnresponse
import boto3
import os
import sys
import json
from urllib.request import urlopen
from zipfile import ZipFile, ZIP_DEFLATED
import io
from io import BytesIO

iotClient = boto3.client('iot')
s3Client = boto3.client('s3')

resourceTag = os.environ['ResourceTag']
bucket = os.environ['BootstrapCertsBucket']
account = os.environ['Account']
region = os.environ['Region']
registrationRoleArn = os.environ['RegistrationRoleArn']
prodLambdaHookArn = os.environ['ProdLambdaHookArn']
rotateLambdaHookArn = os.environ['RotateLambdaHookArn']

bootstrapPolicyName = '{}_birth_policy'.format(resourceTag)
productionPolicyName = '{}_prod_policy'.format(resourceTag)

prodTemplateName = '{}_prod_template_CFN'.format(resourceTag)
rotateTemplateName = '{}_rotation_template_CFN'.format(resourceTag)

prodTemplateArn = 'arn:aws:iot:{}:{}:provisioningtemplate/{}'.format(
    region, account, prodTemplateName)
rotateTemplateArn = 'arn:aws:iot:{}:{}:provisioningtemplate/{}'.format(
    region, account, rotateTemplateName)

bootstrapPrefix = 'bootstrap'
rootCertUrl = "https://www.amazontrust.com/repository/AmazonRootCA1.pem"
certLocation = "certs/bootstrap-certificate.pem.crt"
keyLocation = "certs/bootstrap-private.pem.key"
scriptPath = os.path.dirname(__file__)


def s3Put(bucket, key, body):
    s3Client.put_object(
        Body=body,
        Bucket=bucket,
        Key=key
    )


def s3UploadFileObject(data, key):
    s3Client.upload_fileobj(data, bucket, key)


def s3List():
    return s3Client.list_objects(
        Bucket=bucket
    )


def s3Delete(bucket, key):
    s3Client.delete_object(
        Bucket=bucket,
        Key=key
    )


def clearBootstrapPolicy():
    items = s3List()
    for key in items['Contents']:
        if key['Key'].split('/')[-1].split('.')[1] == 'id':
            certId = key['Key'].split('/')[-1].split('.')[0]

    iotClient.update_certificate(
        certificateId=certId,
        newStatus='INACTIVE'
    )
    iotClient.delete_certificate(
        certificateId=certId,
        forceDelete=True
    )
    for fileobject in items['Contents']:
        s3Delete(bucket, fileobject['Key'])

    iotClient.delete_provisioning_template(
        templateName=prodTemplateName
    )

    iotClient.delete_provisioning_template(
        templateName=rotateTemplateName
    )
    iotClient.delete_policy(
        policyName=bootstrapPolicyName
    )
   


def getIoTEndpoint():
    result = iotClient.describe_endpoint(
        endpointType='iot:Data-ATS'
    )
    return result['endpointAddress']


def updateConfig(fullPath, filename, iotEndpoint):
    with open(fullPath, 'r') as config:
        data = config.read()
    if filename == 'config.ini':
        data = data.replace('$ENTER_ENDPOINT_HERE', iotEndpoint)
        data = data.replace('$ENTER_TEMPLATE_NAME_HERE', prodTemplateName)
        data = data.replace('$ENTER_CERT_ROTATION_TEMPLATE_HERE', rotateTemplateName)
    return data


def createClient(certificates, iotEndpoint):
    mem_zip = BytesIO()
    clientDir = "{}/{}".format(scriptPath, 'client')

    with ZipFile(mem_zip, mode="w", compression=ZIP_DEFLATED) as client:
        for root, subFolder, files in os.walk(clientDir):
            for file in files:
                fullPath = root + '/' + file
                data = updateConfig(fullPath, file, iotEndpoint)
                client.writestr(fullPath.split('client/')[1], data)
        print('got to here')
        client.writestr(certLocation, certificates['certificatePem'])
        client.writestr(keyLocation, certificates['keyPair']['PrivateKey'])
        rootCert = urlopen(rootCertUrl)
        client.writestr("certs/root.ca.pem", rootCert.read())
    mem_zip.seek(0)
    return mem_zip


def createBootstrapPolicy():
    with open('artifacts/bootstrapPolicy.json', 'r') as bsp:
        bootstrapPolicy = bsp.read().replace(
            '$REGION:$ACCOUNT', '{}:{}'.format(region, account))
        bootstrapPolicy = bootstrapPolicy.replace(
            '$PROVTEMPLATE', prodTemplateName)

        bootstrapPolicy = json.loads(bootstrapPolicy)

    certificates = iotClient.create_keys_and_certificate(
        setAsActive=True
    )
    iotClient.create_policy(
        policyName=bootstrapPolicyName,
        policyDocument=json.dumps(bootstrapPolicy)
    )
    iotClient.attach_policy(
        policyName=bootstrapPolicyName,
        target=certificates['certificateArn']
    )

    return certificates


def createProductionPolicy():
    with open('artifacts/productionPolicy.json', 'r') as pp:
        productionPolicy = pp.read().replace(
            '$REGION:$ACCOUNT', '{}:{}'.format(region, account))
        productionPolicy = productionPolicy.replace(
            '$PROVTEMPLATE', rotateTemplateName)
        productionPolicy = json.loads(productionPolicy)

    iotClient.create_policy(
        policyName=productionPolicyName,
        policyDocument=json.dumps(productionPolicy)
    )


def uploadClientToS3(certificates, client):
    Id = certificates['certificateId']
    s3Put(bucket, "{}/{}.id".format(bootstrapPrefix, Id), Id)
    s3UploadFileObject(client, 'client.zip')


def createTemplateBody(filePath):
    with open(filePath, 'r') as pt:
        provisioningTemplate = json.load(pt)
    provisioningTemplate['Resources']['policy']['Properties']['PolicyName'] = productionPolicyName
    print(provisioningTemplate)
    return provisioningTemplate


def createTemplate(templateBody, templateName, lambdaHookArn):
    print(templateBody)
    print(templateName)
    print(lambdaHookArn)
    iotClient.create_provisioning_template(
        templateName=templateName,
        description=resourceTag + ' Provisioning Template',
        templateBody=json.dumps(templateBody),
        enabled=True,
        provisioningRoleArn=registrationRoleArn,
        preProvisioningHook={
            'targetArn': lambdaHookArn
        }
    )

def createModelBootstraps():
    model_bucket = '{}-per-vendor-bootstraps'.format(resourceTag)
    
    with open('artifacts/models.txt', 'r') as rows:
        s3Client.create_bucket(Bucket=model_bucket)
        models = rows.read().splitlines()
        rootCert = urlopen(rootCertUrl)
        
        for model in models:
            #create certificates
            certificates = iotClient.create_keys_and_certificate(setAsActive=True)
            iotClient.attach_policy(policyName=bootstrapPolicyName,target=certificates['certificateArn'])
            mem_zip = BytesIO()
            
            with ZipFile(mem_zip, mode="w", compression=ZIP_DEFLATED) as archive:
                archive.writestr('bootstrap-certificate.pem.crt', certificates['certificatePem'])
                archive.writestr('bootstrap-private.pem.key', certificates['keyPair']['PrivateKey'])
                archive.writestr('root.ca.pem', rootCert.read())
            mem_zip.seek(0)
            s3Client.upload_fileobj(mem_zip, model_bucket,'{0}/{0}_bootstraps.zip'.format(model))

def handler(event, context):
    responseData = {}
    print(event)
    try:

        result = cfnresponse.FAILED
        if event['RequestType'] == 'Create':
            certificates = createBootstrapPolicy()
            createProductionPolicy()
            iotEndpoint = getIoTEndpoint()
            print('iotendpoint')
            client = createClient(certificates, iotEndpoint)
            print('client created')
            uploadClientToS3(certificates, client)
            print('client uploaded')
            #create provisioning templates
            prodTemplateBody = createTemplateBody('artifacts/provisioningTemplate.json')
            createTemplate(prodTemplateBody, prodTemplateName, prodLambdaHookArn)
            rotateTemplateBody = createTemplateBody('artifacts/certRotationTemplate.json')
            createTemplate(rotateTemplateBody, rotateTemplateName, rotateLambdaHookArn)
            createModelBootstraps()
            result = cfnresponse.SUCCESS
        elif event['RequestType'] == 'Update':
            #create provisioning templates
            print('UPDATE FIRED!')
            createModelBootstraps()
            result = cfnresponse.SUCCESS
        else:
            clearBootstrapPolicy()
            result = cfnresponse.SUCCESS

    except Exception as e:
        print('error', e)
        result = cfnresponse.FAILED

    sys.stdout.flush()
    print(responseData)
    cfnresponse.send(event, context, result, responseData)
