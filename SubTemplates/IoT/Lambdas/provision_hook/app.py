import json

provision_response = {'allowProvisioning': False}


def handler(event, context):

    # Future log Cloudwatch logs
    print("Received event: " + json.dumps(event, indent=2))

    ### Validate the claim with extreme prejudice here against back-end logic and whitelisting.
    ### If good ...
    provision_response["allowProvisioning"] = True

    return provision_response