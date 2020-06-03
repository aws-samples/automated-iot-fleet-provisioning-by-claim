import json

provision_response = {'allowProvisioning': False}


def handler(event, context):

    # Future log Cloudwatch logs
    print("Received event: " + json.dumps(event, indent=2))

    # just pass it through
    provision_response["allowProvisioning"] = True

    return provision_response
