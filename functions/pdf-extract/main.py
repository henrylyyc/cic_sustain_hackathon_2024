import boto3
import time
import json
from fpdf import FPDF
from datetime import datetime
import io 

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
    You are the Secretary-General of the United Nations, focusing on the UN Sustainable Development Goals (SDGs). 
    We are evaluating a user's project report aimed at addressing one or more UN SDGs. 
    Your task is to determine a relevancy score for each user-defined SDG and provide constructive feedback to help the user improve their relevancy score.
    Your objective is to determine a relevancy score for each user-defined SDG based on a structured chain of reasoning.

    Evaluation Steps:

    Identify User-Defined SDGs:
    If the user has defined SDGs, analyze each one separately. If none are provided, identify and present the top two most relevant SDGs based on the content of their report.

    Assess Targets:
    For each SDG, identify the relevant targets that the project addresses. It is possible for the project to address all the goals. Count the number of targets as your initial score.

    Evaluate Indicators:
    For each target, consider the associated indicators. We can consider up to all of the indicators. Assess how many indicators the project is likely to impact positively on both a regional and global scale. Adjust the initial score based on this analysis.

    Calculate Final Score:
    Combine the initial target count with the adjusted indicator impact to arrive at a percentage score that reflects the project's relevancy to the SDG.

    Provide Constructive Feedback:
    Along with the score, offer specific suggestions on how the project could enhance its alignment with the SDGs.

    Please express your final score in the format <answer>tags</answer>.

    Example Input: <targeted SDGs> SDG 2, 6, and 7 </targeted SDGs>

    <proposal>... [Project proposal here] ...</proposal> 

    For each SDG, clearly outline your reasoning in <thinking>tags</thinking>, detailing the identified targets and their indicators.
    Conclude with your calculated score in <answer>tags</answer>.
    Your assessment will provide valuable insights to the user, enabling them to refine their project’s alignment with the SDGs and maximize its impact. Provide feedback that is succinct and to the point.
    """
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
    
    except error as e:
        print(f"Error starting evaluating job: {e}")
        return None
        
def create_pdf(s3_bucket, s3_key, sdg_data):
    pdf = FPDF()
    page_width = pdf.w + 30
    page_height = pdf.h
    pdf.add_page()
    pdf.set_font("Arial", size=15, style='B')
    pdf.cell(200, 10, txt="Report Summary", ln=True, align='C')
    p(pdf, 200, 5, 'C', datetime.today().strftime('%Y-%m-%d'))
    p(pdf, 200, 10, 'C', "")
    generateTextHorizontal(
        page_width,
        "Please note that this report was generated by GenAI. It provides a preliminary validation of the project along with suggestions for improvement.",
        pdf,
        200,
        5,
        'L'
    )
    for sdg in sdg_data:
        p(pdf, 200, 10, 'C',"")
        h2(pdf, 200, 10, 'L', f"SDG {sdg['SDG']}")
        pdf.cell(0, 0.5, txt="", ln=True, align='C', fill=True)
        p(pdf, 200, 5, 'L', f"Relevancy Score: {sdg['Relevancy Score']}")
        generateTextHorizontal(page_width, f"Feedback: {sdg['Feedback']}", pdf, 200, 5, 'L')
        for target, details in sdg['Targets'].items():
            p(pdf, 200, 5, 'L', f"Target: {target}")
            p(pdf, 200, 5, 'L', f"Satisfied: {'Yes' if details['Satisfied'] else 'No'}")
            generateTextHorizontal(page_width, f"Relevant Text: {details['Relevant Text']}", pdf, 200, 5, 'L')
        if pdf.get_y() > (page_height - 20):
            pdf.add_page()

    # Write PDF to a BytesIO buffer
    pdf_buffer = io.BytesIO()
    pdf_output = pdf.output(dest='S').encode('latin1')  # Output as bytes in Latin-1 encoding
    pdf_buffer.write(pdf_output)
    pdf_buffer.seek(0)

    # Upload the buffer to S3
    s3 = boto3.client('s3')
    s3.put_object(Bucket=s3_bucket, Key=s3_key, Body=pdf_buffer, ContentType='application/pdf')

    # Generate a presigned URL for the file
    file_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': s3_bucket, 'Key': s3_key},
        ExpiresIn=3600  # URL expiration time in seconds (1 hour)
    )

    return file_url
    
def h1(pdf, h, v, a, text: str):
    pdf.set_font("Arial", size=14, style='B')
    pdf.cell(h, v, text, ln=True, align=a)

def h2(pdf, h, v, a, text: str):
    pdf.set_font("Arial", size=12, style='B')
    pdf.cell(h, v, text, ln=True, align=a)

def p(pdf, h, v, a, text: str):
    pdf.set_font("Arial", size=10)
    pdf.cell(h, v, text, ln=True, align=a)

def generateTextHorizontal(pdfWidth, text, pdf, h, v, a):
    l = int(pdfWidth / 2)
    start = 0
    i = l
    text = list(text)
    
    while i < len(text):
        for j in range(i, start, -1):
            if text[j] == ' ':
                p(pdf, h, v, a, ''.join(text[start:j]))
                start = j + 1
                break
        else:
            p(pdf, h, v, a, ''.join(text[start:i]))
            start = i
        i = start + l
    if start < len(text):
        p(pdf, h, v, a, ''.join(text[start:]))


def main():
    # Start Textract job
    # extracted_text = extract_text_from_pdf(BUCKET_NAME, FILE_NAME)
    # print(extracted_text)
    # evaluated_text1 = evaluated_text(extracted_text)
    # print(evaluated_text1)
    
    # Create a PDF
    
    sdg_data = [
        {
            "SDG": 1,
            "Relevancy Score": 85,
            "Feedback": "This SDG has high relevance for the project.",
            "Targets": {
                "Target 1.1": {"Satisfied": True, "Relevant Text": "This target is fully satisfied."},
                "Target 1.2": {"Satisfied": False, "Relevant Text": "This target is partially relevant."}
            }
        },
        {
            "SDG": 2,
            "Relevancy Score": 60,
            "Feedback": "This SDG is moderately relevant for the project.",
            "Targets": {
                "Target 2.1": {"Satisfied": True, "Relevant Text": "This target is met, but further efforts are needed."},
                "Target 2.2": {"Satisfied": False, "Relevant Text": "This target has not been fully addressed yet."}
            }
        },
        {
            "SDG": 1,
            "Relevancy Score": 85,
            "Feedback": "This SDG has high relevance for the project.",
            "Targets": {
                "Target 1.1": {"Satisfied": True, "Relevant Text": "This target is fully satisfied."},
                "Target 1.2": {"Satisfied": False, "Relevant Text": "This target is partially relevant."}
            }
        },
        {
            "SDG": 2,
            "Relevancy Score": 60,
            "Feedback": "This SDG is moderately relevant for the project.",
            "Targets": {
                "Target 2.1": {"Satisfied": True, "Relevant Text": "This target is met, but further efforts are needed."},
                "Target 2.2": {"Satisfied": False, "Relevant Text": "This target has not been fully addressed yet."}
            }
        },
        {
            "SDG": 1,
            "Relevancy Score": 85,
            "Feedback": "This SDG has high relevance for the project. This SDG has high relevance for the project. This SDG has high relevance for the project. This SDG has high relevance for the project.",
            "Targets": {
                "Target 1.1": {"Satisfied": True, "Relevant Text": "This target is fully satisfied."},
                "Target 1.2": {"Satisfied": False, "Relevant Text": "This target is partially relevant."}
            }
        },
        {
            "SDG": 2,
            "Relevancy Score": 60,
            "Feedback": "This SDG is moderately relevant for the project.",
            "Targets": {
                "Target 2.1": {"Satisfied": True, "Relevant Text": "This target is met, but further efforts are needed."},
                "Target 2.2": {"Satisfied": False, "Relevant Text": "This target has not been fully addressed yet."}
            }
        }
    ]

    # Upload the PDF directly to S3
    s3_key = 'report-'+FILE_NAME
    url = create_pdf(BUCKET_NAME, s3_key, sdg_data)
    print("url: ", url)

    

