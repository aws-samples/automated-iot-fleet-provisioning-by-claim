import json
import boto3
from datetime import date, datetime, timedelta

client = boto3.client('iot')
endpoint = boto3.client('iot-data')

#used to validate device actually needs a new cert
CERT_ROTATION_DAYS = 360

#validation check date for registry query
target_date = date.today()-timedelta(days=CERT_ROTATION_DAYS)
target_date = target_date.strftime("%Y%m%d")


#short hand date
d = date.today()

#Set up payload with new cert issuance date
provision_response = {'allowProvisioning': False, "parameterOverrides": {
    "CertDate": date.today().strftime("%Y%m%d")}}


def handler(event, context):

    # Future log Cloudwatch logs
    print("Received event: " + json.dumps(event, indent=2))

    thing_name = event['parameters']['DeviceSerial']
    response = client.describe_thing(
    thingName=thing_name)
 
    try:
      #Cross reference ID of requester with entry in registery to ensure device needs a rotation.
      if int(response['attributes']['cert_issuance']) < int(target_date):
        deactivate_cert(thing_name)
        provision_response["allowProvisioning"] = True
    except:
      provision_response["allowProvisioning"] = False

    return provision_response

def deactivate_cert(thing_id):

  #Get all the certificates for a thing
  principals = client.list_thing_principals(
    thingName=thing_id
  )
 
  #Describe each certificate
  for arn in principals['principals']:
    cert_id = strip_arn(arn)
    cert = client.describe_certificate(
      certificateId=cert_id
    )
    
    #strip timezone awareness for date compare
    cert_date = cert['certificateDescription']['creationDate'].replace(tzinfo=None)
  
    #Deactivate old certificates
    if cert_date < datetime.now() - timedelta(minutes=5):
      print(cert['certificateDescription']['creationDate'])
      client.update_certificate(certificateId=cert['certificateDescription']['certificateId'],newStatus='INACTIVE')
      client.detach_thing_principal(thingName=thing_id, principal=arn)
      

def strip_arn(arn):
  index = arn.index('/') + 1
  return arn[index:]