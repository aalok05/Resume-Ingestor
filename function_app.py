import azure.functions as func
import base64
import pymupdf
import logging
import json
import uuid
import re
from datetime import datetime
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError
from openai import AzureOpenAI
import os

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="ingestresume",methods=["POST"])
def ingestresume(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        # Get the request body and parse JSON
        req_body = req.get_json()
        
        if not req_body:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "Invalid JSON in request body"
                }),
                mimetype="application/json",
                status_code=400
            )
        
        # Extract FileUrl and FileContent from request
        file_url = req_body.get("FileUrl", "")
        file_content = req_body.get("FileContent", "")
        external = req_body.get("External", False)  # Default to False if not provided
        
        if not file_content:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": "FileContent is required"
                }),
                mimetype="application/json",
                status_code=400
            )
        
        # Decode base64 PDF
        pdf_bytes = base64.b64decode(file_content)
        
        doc = pymupdf.Document(stream=pdf_bytes, filetype="pdf") # Open the PDF file

        # Initialize text variable to store all extracted text
        extracted_text = ""
        
        # Iterate through pages and extract text
        for page in doc:
            text = page.get_text()  # get plain text
            extracted_text += text + "\n"  # add page text with newline separator
        
        # Close the document
        doc.close()
        
        # Upload to Cosmos DB for vectorization
        cosmos_result = upload_to_cosmos_db(file_url, extracted_text, external)
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "file_url": file_url,
                "external": external,
                "extracted_text_length": len(extracted_text),
                "cosmos_document_id": cosmos_result.get("id"),
                "candidate_info": {
                    "name": cosmos_result.get("personalInfo", {}).get("name", ""),
                    "email": cosmos_result.get("personalInfo", {}).get("email", ""),
                    "location": cosmos_result.get("personalInfo", {}).get("location", ""),
                    "total_experience_years": cosmos_result.get("experience", {}).get("total_years", 0),
                    "current_role": cosmos_result.get("experience", {}).get("current_role", ""),
                    "technical_skills_count": len(cosmos_result.get("skills", {}).get("technical_skills", [])),
                    "soft_skills_count": len(cosmos_result.get("skills", {}).get("soft_skills", [])),
                    "certifications_count": len(cosmos_result.get("certifications", [])),
                    "industries": cosmos_result.get("experience", {}).get("industries", [])
                },
                "message": "Resume processed and uploaded to Cosmos DB successfully"
            }),
            mimetype="application/json",
            status_code=200
        )
        
    except json.JSONDecodeError:
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "Invalid JSON format in request body"
            }),
            mimetype="application/json",
            status_code=400
        )
    except Exception as e:
        logging.error(f"Error processing PDF: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": f"Error processing PDF: {str(e)}"
            }),
            mimetype="application/json",
            status_code=400
        )

def extract_resume_data_with_ai(resume_text: str) -> dict:
    """
    Extract skills, experience, education, and keywords from resume text using Azure OpenAI
    """
    try:
        # Initialize Azure OpenAI client
        azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        azure_openai_key = os.environ.get("AZURE_OPENAI_KEY")
        azure_openai_deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
        azure_openai_api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        
        if not azure_openai_endpoint or not azure_openai_key:
            raise ValueError("Azure OpenAI connection settings not found in environment variables")
        
        client = AzureOpenAI(
            azure_endpoint=azure_openai_endpoint,
            api_key=azure_openai_key,
            api_version=azure_openai_api_version
        )
        
        # Create prompt for extracting structured data according to new schema
        prompt = f"""
        Analyze the following resume text and extract structured information. Return the response as a valid JSON object with the following structure:

        {{
            "personalInfo": {{
                "name": "Full name of the candidate",
                "email": "email address if found",
                "location": "city, state/country if found"
            }},
            "skills": {{
                "technical_skills": [
                    {{"skill": "skill name", "proficiency": "Beginner|Intermediate|Advanced|Expert", "years": estimated_years}}
                ],
                "soft_skills": ["list of soft skills like Leadership, Communication, etc."]
            }},
            "experience": {{
                "total_years": number_of_years,
                "current_role": "most recent job title",
                "industries": ["list of industries worked in"]
            }},
            "certifications": ["list of certifications if any"],
            "searchable_keywords": ["important keywords for search"]
        }}

        Instructions:
        - For technical skills, estimate proficiency based on context, years mentioned, or job responsibilities
        - For years of experience per skill, estimate based on job history and mentions in resume
        - Extract total years of experience from the entire career
        - Identify current/most recent role from work history
        - List industries the candidate has worked in
        - Include both technical and soft skills
        - Generate searchable keywords that would help find this candidate

        Resume Text:
        {resume_text[:6000]}
        """
        
        # Make API call to Azure OpenAI
        response = client.chat.completions.create(
            model=azure_openai_deployment,
            messages=[
                {"role": "system", "content": "You are an expert resume parser. Extract structured information from resumes and return valid JSON only. Be precise with proficiency levels and experience years."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096,
            temperature=0.1,
            top_p=1.0
        )
        
        # Parse the response
        ai_response = response.choices[0].message.content
        
        # Handle None response
        if ai_response is None:
            ai_response = ""
        
        # Clean the response to ensure it's valid JSON
        if ai_response.startswith("```json"):
            ai_response = ai_response[7:]
        if ai_response.endswith("```"):
            ai_response = ai_response[:-3]
        
        ai_response = ai_response.strip()
        
        # Parse JSON response
        extracted_data = json.loads(ai_response)
        
        logging.info(f"AI extraction successful: {len(extracted_data.get('skills', {}).get('technical_skills', []))} technical skills extracted")
        
        return extracted_data
        
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse AI response as JSON: {str(e)}")
        logging.error(f"AI Response: {ai_response}")
        # Return basic fallback structure
        return {
            "personalInfo": {"name": "", "email": "", "location": ""},
            "skills": {"technical_skills": [], "soft_skills": []},
            "experience": {"total_years": 0, "current_role": "", "industries": []},
            "certifications": [],
            "searchable_keywords": []
        }
    except Exception as e:
        logging.error(f"Error extracting data with AI: {str(e)}")
        # Return basic fallback structure
        return {
            "personalInfo": {"name": "", "email": "", "location": ""},
            "skills": {"technical_skills": [], "soft_skills": []},
            "experience": {"total_years": 0, "current_role": "", "industries": []},
            "certifications": [],
            "searchable_keywords": []
        }

def upload_to_cosmos_db(file_url: str, resume_text: str, external: bool) -> dict:
    """
    Upload resume text and file URL to Cosmos DB for vectorization
    """
    try:
        # Get Cosmos DB connection settings from environment variables
        cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT")
        cosmos_key = os.environ.get("COSMOS_KEY")
        database_name = os.environ.get("COSMOS_DATABASE_NAME", "exploredb")
        container_name = os.environ.get("COSMOS_CONTAINER_NAME", "resumes")
        
        if not cosmos_endpoint or not cosmos_key:
            raise ValueError("Cosmos DB connection settings not found in environment variables")
        
        # Initialize Cosmos DB client
        cosmos_client = CosmosClient(cosmos_endpoint, cosmos_key)
        
        # Get database and container
        database = cosmos_client.get_database_client(database_name)
        container = database.get_container_client(container_name)
        
        # Extract filename from SharePoint URL for better searchability
        filename = ""
        if file_url:
            filename = file_url.split("/")[-1] if "/" in file_url else file_url
        
        # Extract data using AI
        ai_extracted_data = extract_resume_data_with_ai(resume_text)
        
        # Generate searchable text from extracted data
        searchable_parts = []
        
        # Add personal info
        personal_info = ai_extracted_data.get("personalInfo", {})
        if personal_info.get("name"):
            searchable_parts.append(personal_info["name"].lower())
        if personal_info.get("location"):
            searchable_parts.append(personal_info["location"].lower())
        
        # Add technical skills
        technical_skills = ai_extracted_data.get("skills", {}).get("technical_skills", [])
        for skill_obj in technical_skills:
            if isinstance(skill_obj, dict) and "skill" in skill_obj:
                searchable_parts.append(skill_obj["skill"].lower())
        
        # Add soft skills
        soft_skills = ai_extracted_data.get("skills", {}).get("soft_skills", [])
        searchable_parts.extend([skill.lower() for skill in soft_skills])
        
        # Add experience info
        experience = ai_extracted_data.get("experience", {})
        if experience.get("current_role"):
            searchable_parts.append(experience["current_role"].lower())
        
        industries = experience.get("industries", [])
        searchable_parts.extend([industry.lower() for industry in industries])
        
        # Add certifications
        certifications = ai_extracted_data.get("certifications", [])
        searchable_parts.extend([cert.lower() for cert in certifications])
        
        # Add searchable keywords
        keywords = ai_extracted_data.get("searchable_keywords", [])
        searchable_parts.extend([keyword.lower() for keyword in keywords])
        
        # Create final searchable text
        searchable_text = " ".join(set(searchable_parts))  # Remove duplicates
        
        # Create document according to new schema
        document = {
            "id": str(uuid.uuid4()),
            "partition_key": "active",
            "external": external,
            "personalInfo": {
                "name": personal_info.get("name", ""),
                "email": personal_info.get("email", ""),
                "location": personal_info.get("location", "")
            },
            "skills": {
                "technical_skills": technical_skills,
                "soft_skills": soft_skills
            },
            "experience": {
                "total_years": experience.get("total_years", 0),
                "current_role": experience.get("current_role", ""),
                "industries": industries
            },
            "certifications": certifications,
            "searchable_text": searchable_text,
            
            # Additional metadata for system use
            "metadata": {
                "fileUrl": file_url,
                "filename": filename,
                "originalContent": resume_text,
                "contentLength": len(resume_text),
                "uploadTimestamp": datetime.utcnow().isoformat(),
                "source": "sharepoint_pdf",
                "processingMethod": "pymupdf",
                "extractionMethod": "azure_openai",
                "version": "3.0",
                "contentType": "application/pdf",
                "aiProcessed": True
            }
        }
        
        # Upload to Cosmos DB
        result = container.create_item(document)
        
        logging.info(f"Successfully uploaded resume to Cosmos DB with ID: {result['id']}")
        logging.info(f"Candidate: {personal_info.get('name', 'Unknown')}")
        logging.info(f"Technical skills: {len(technical_skills)}")
        logging.info(f"Total experience: {experience.get('total_years', 0)} years")
        logging.info(f"Current role: {experience.get('current_role', 'Unknown')}")
        
        return result
        
    except CosmosHttpResponseError as e:
        logging.error(f"Cosmos DB error: {str(e)}")
        raise Exception(f"Failed to upload to Cosmos DB: {str(e)}")
    except Exception as e:
        logging.error(f"Error uploading to Cosmos DB: {str(e)}")
        raise Exception(f"Failed to upload to Cosmos DB: {str(e)}") 