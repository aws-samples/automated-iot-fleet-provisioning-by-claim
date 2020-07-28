import json
import boto3
from datetime import date, datetime, timedelta

client = boto3.client('iot')
endpoint = boto3.client('iot-data')

#Set Cert Rotation Interval
CERT_ROTATION_DAYS = 360
GRACE_PERIOD = 14

#Thingname will be post-pended
ALERT_TOPIC = 'admin/alerts'

#short hand date
d = date.today()

#Check for certificate expiry
target_date = d-timedelta(days=CERT_ROTATION_DAYS)

#Set up deactivation trigger
trigger_date = target_date-timedelta(days=GRACE_PERIOD)

#Convery to numeric format
target_date = target_date.strftime("%Y%m%d")
trigger_date = trigger_date.strftime("%Y%m%d")


def handler(event, context):
  
  overdue_things = get_overdue_things(target_date)
 
  for thing in overdue_things['things']:
    print(thing)
    endpoint.publish(
      topic='{}/{}'.format(ALERT_TOPIC,thing['thingName']),
      payload='{"msg":"rotate_cert"}'
      )
    
    if thing['attributes']["cert_issuance"] >= trigger_date:
      deactivate_cert(thing['thingName'])
  
  return {
    'notified_things': overdue_things['things']
    
  }


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
      activation_response = client.update_certificate(
        certificateId=cert['certificateDescription']['certificateId'],
        newStatus='INACTIVE')
      client.detach_thing_principal(thingName=thing_id, principal=arn)
  
  
def get_overdue_things(by_date):
  response = client.search_index(
    queryString='attributes.cert_issuance<{}'.format(by_date),
    maxResults=500) 
  return response
  
def strip_arn(arn):
  index = arn.index('/') + 1
  return arn[index:]