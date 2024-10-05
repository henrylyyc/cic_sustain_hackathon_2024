import boto3
import time

TEXTRACT = boto3.client('textract')
BUCKET = boto3.client('s3')
REGION = "us-west-2"
BUCKET_NAME = "pdf-extract-oct-5-2024-11-45-bucket"
FILE_NAME = "project-proposal-2.pdf" # TODO: Parametized thi part

def lambda_handler(event, context):
    main()
    
    return {
        'statusCode': 200,
        'body': 'Success'
    }
    
def extract_text_from_pdf(bucket_name, object_name):
    # Start Textract job
    try:
        response = TEXTRACT.start_document_text_detection(
            DocumentLocation={
                'S3Object': {
                    'Bucket': bucket_name,
                    'Name': object_name
                }
            }
        )

        job_id = response['JobId']
        print(f"Started Textract job with JobId: {job_id}")
    except Exception as e:
        print(f"Error starting Textract job: {e}")
        return

    # Wait for Textract job to complete
    print("Waiting for Textract job to complete...")
    while True:
        response = TEXTRACT.get_document_text_detection(JobId=job_id)
        status = response['JobStatus']
        if status in ['SUCCEEDED', 'FAILED']:
            break
        print("Job in progress, waiting...")
        time.sleep(5)

    if status == 'SUCCEEDED':
        print("Textract job completed successfully.")
        
        # Retrieve and process all pages
        extracted_text = ""
        next_token = None
        while True:
            if next_token:
                response = TEXTRACT.get_document_text_detection(JobId=job_id, NextToken=next_token)
            else:
                response = TEXTRACT.get_document_text_detection(JobId=job_id)

            for block in response['Blocks']:
                if block['BlockType'] == 'LINE':
                    extracted_text += block['Text'] + "\n"

            next_token = response.get('NextToken')
            if not next_token:
                break

        return extracted_text
    else:
        print("Textract job failed.")
        return None

def main():
    # Start Textract job
    extracted_text = extract_text_from_pdf(BUCKET_NAME, FILE_NAME)

    print(extracted_text)

