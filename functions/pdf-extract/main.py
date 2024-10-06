import boto3
import time
import json

TEXTRACT = boto3.client('textract')
BUCKET = boto3.client('s3')
REGION = "us-west-2"
BUCKET_NAME = "pdf-extract-oct-5-2024-11-45-bucket"
FILE_NAME = "project-proposal-2.pdf" # TODO: Parametized thi part

def lambda_handler(event, context):
    print("event: ", event)
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

def evaluated_text(extracted_text):
    try:
        bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')
        prompt = """
    You are the Secretary-General of the United Nations, focusing on the UN Sustainable Development Goals (SDGs). We are evaluating a user's project report aimed at addressing one or more UN SDGs. Your task is to determine a relevancy score for each user-defined SDG and provide constructive feedback to help the user improve their relevancy score.

Your objective is to determine a relevancy score for each user-defined SDG based on a structured chain of reasoning. 

Evaluation Steps:

1. Identify User-Defined SDGs:
If the user has defined SDGs, analyze each one separately. If none are provided, identify and present the top two most relevant SDGs based on the content of their report.

2. Assess Targets:
For each SDG, identify the relevant targets that the project addresses. It is possible for each target to be addressed (e.g., a project targeting SDG 2 can address some or all of targets 2.1, 2.2, 2.3, 2.4, 2.5, 2.a, 2.b, and 2.c). Count the number of targets as your initial score. 

3. Analyze Input Text:
For each target that you believe is being addressed by the project, review the input proposal to find text sections of no more than 3 sentences that indicate the proposal meets the target's definition. Do not consider sections of the proposal that contain SDG. For example, for a target "By 2030, substantially increase water-use efficiency across all sectors and ensure sustainable withdrawals and supply of freshwater to address water scarcity and substantially reduce the number of people suffering from water scarcity", we would expect the most relevant text to be related to increasing water-use efficiency.  Remember this text section as [message].

4. Evaluate Indicators:
For each target, consider the associated indicators. We can consider up to all of the indicators. Assess how many indicators the project is likely to impact positively on both a regional and global scale. Adjust the initial score based on this analysis.

5. Calculate Final Score:
Combine the initial target count with the adjusted indicator impact to arrive at a percentage score that reflects the project's relevancy to each SDG.

6. Provide Constructive Feedback:
Along with the score, offer specific suggestions on how the project could enhance its alignment with each specific SDG.

Example Input: 
<input>
<targeted SDGs> SDG 2, 6, and 7 </targeted SDGs>
<proposal>... [Project proposal here] ...</proposal> 
</input>

For each SDG, follow the evaluation steps, thinking step-by-step. Do not output this thinking. Output your conclusions for each SDG in one <answer> tag, using the following JSON format:

{
"SDG": SDG Number,
"Relevancy Score": Relevancy Score,
"Feedback": Feedback,
"Targets": {"Target[i for all targets in (SDG Number)]": {"Satisfied": boolean, "Relevant Text": "[message]"}}
}

Ensure to include all targets for the SDG, satisfied or not, for each specific targeted SDG in the JSON output (e.g., for SDG 2, 2.1, 2.2, 2.3, 2.4, 2.5, 2.a, 2.b, and 2.c). Your assessment will provide valuable insights to the user, enabling them to refine their project’s alignment with each SDG and maximize its impact. Provide feedback that is succinct and to the point, without summarizing existing information. Only provide feedback that is new and that provide insights."""
        model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
        full_prompt = f"{prompt}<proposal>{extracted_text}</proposal>"
    
        kwargs = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "temperature": 0.5,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": full_prompt}]
                }
            ],
        }
    
        try:
            # Invoke the Bedrock model
            response = bedrock_runtime.invoke_model(modelId=model_id, body=json.dumps(kwargs))
            # print("ch")
            # Directly parse the response body
            response_body = json.loads(response['body'].read())  # Removed .read()
            # print("aa")
            # Extract the relevant text from the response
            response_text = response_body.get("content", [{}])[0].get("text", "")
            # print("ss")
            # print ("chchchc",response_text)
            return response_text

        except Exception as e:
            print("failed")
            return None
    
    except Exception as e:
        print(f"Error starting evaluating job: {e}")
        return None
        


def main():
    # Start Textract job
    extracted_text = extract_text_from_pdf(BUCKET_NAME, FILE_NAME)
    print(extracted_text)
    evaluated_text1 = evaluated_text(extracted_text)
    print(evaluated_text1)
    # bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-west-2')
    # prompt = """
    # You are the Secretary-General of the United Nations, focusing on the UN Sustainable Development Goals (SDGs). 
    # We are evaluating a user's project report aimed at addressing one or more UN SDGs. 
    # Your task is to determine a relevancy score for each user-defined SDG and provide constructive feedback to help the user improve their relevancy score.
    # Your objective is to determine a relevancy score for each user-defined SDG based on a structured chain of reasoning.

    # Evaluation Steps:

    # Identify User-Defined SDGs:
    # If the user has defined SDGs, analyze each one separately. If none are provided, identify and present the top two most relevant SDGs based on the content of their report.

    # Assess Targets:
    # For each SDG, identify the relevant targets that the project addresses. It is possible for the project to address all the goals. Count the number of targets as your initial score.

    # Evaluate Indicators:
    # For each target, consider the associated indicators. We can consider up to all of the indicators. Assess how many indicators the project is likely to impact positively on both a regional and global scale. Adjust the initial score based on this analysis.

    # Calculate Final Score:
    # Combine the initial target count with the adjusted indicator impact to arrive at a percentage score that reflects the project's relevancy to the SDG.

    # Provide Constructive Feedback:
    # Along with the score, offer specific suggestions on how the project could enhance its alignment with the SDGs.

    # Please express your final score in the format <answer>tags</answer>.

    # Example Input: <targeted SDGs> SDG 2, 6, and 7 </targeted SDGs>

    # <proposal>... [Project proposal here] ...</proposal> 

    # For each SDG, clearly outline your reasoning in <thinking>tags</thinking>, detailing the identified targets and their indicators.
    # Conclude with your calculated score in <answer>tags</answer>.
    # Your assessment will provide valuable insights to the user, enabling them to refine their project’s alignment with the SDGs and maximize its impact. Provide feedback that is succinct and to the point.
    # """
    # model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    # full_prompt = f"{prompt}<proposal>{extracted_text}</proposal>"
    
    # kwargs = {
    #     "anthropic_version": "bedrock-2023-05-31",
    #     "max_tokens": 512,
    #     "temperature": 0.5,
    #     "messages": [
    #         {
    #             "role": "user",
    #             "content": [{"type": "text", "text": full_prompt}]
    #         }
    #     ],
    # }
    # print("check1")

    # try:
    #     # Invoke the Bedrock model
    #     response = bedrock_runtime.invoke_model(modelId=model_id, body=json.dumps(kwargs))
    #     print("ch")
    #     # Directly parse the response body
    #     response_body = json.loads(response['body'].read())  # Removed .read()
    #     print("aa")
    #     # Extract the relevant text from the response
    #     response_text = response_body.get("content", [{}])[0].get("text", "")
    #     print("ss")
    #     print ("chchchc",response_text)
    #     return {
    #         'statusCode': 200,
    #         'body': json.dumps({'summary': response_text})
    #     }

    # except Exception as e:
    #     return {
    #         'statusCode': 500,
    #         'body': json.dumps({'error': str(e)})
    #     }

    

