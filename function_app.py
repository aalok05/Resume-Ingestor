import azure.functions as func
import base64
import pymupdf
import logging
import json
import uuid
from datetime import datetime
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError
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
        cosmos_result = upload_to_cosmos_db(file_url, extracted_text)
        
        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "file_url": file_url,
                "extracted_text_length": len(extracted_text),
                "cosmos_document_id": cosmos_result.get("id"),
                "extracted_data": {
                    "skills": cosmos_result.get("skills", []),
                    "experience": cosmos_result.get("experience", ""),
                    "education": cosmos_result.get("education", ""),
                    "keywords_count": len(cosmos_result.get("keywords", [])),
                    "word_count": cosmos_result.get("wordCount", 0),
                    "skills_count": cosmos_result.get("analytics", {}).get("skillsCount", 0)
                },
                "message": "Resume processed and uploaded to Cosmos DB for vectorization"
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

def upload_to_cosmos_db(file_url: str, resume_text: str) -> dict:
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
        
        # Basic text analysis for enhanced fields
        words = resume_text.split()
        lines = resume_text.split('\n')
        
        # Extract potential skills (basic keyword matching - can be enhanced with NLP)
        common_skills = [
            "Python", "JavaScript", "Java", "C++", "C#", "React", "Angular", "Vue", 
            "Node.js", "Express", "Django", "Flask", "Spring", "Docker", "Kubernetes",
            "AWS", "Azure", "GCP", "SQL", "MongoDB", "PostgreSQL", "MySQL", "Redis",
            "Git", "Jenkins", "CI/CD", "Agile", "Scrum", "Machine Learning", "AI",
            "Data Science", "Tableau", "Power BI", "Excel", "Project Management"
        ]
        
        detected_skills = []
        for skill in common_skills:
            if skill.lower() in resume_text.lower():
                detected_skills.append(skill)
        
        # Extract basic keywords (most frequent meaningful words)
        import re
        # Remove common stop words and extract meaningful terms
        stop_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an', 'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had'}
        words_clean = [word.lower().strip('.,!?;:"()[]{}') for word in words if len(word) > 3 and word.lower() not in stop_words]
        
        # Get unique words for keywords
        unique_words = list(set(words_clean))
        keywords = unique_words[:20]  # Top 20 unique keywords
        
        # Try to extract experience (basic pattern matching)
        experience = ""
        experience_patterns = [
            r'(\d+)\s*(?:years?|yrs?)\s*(?:of\s*)?experience',
            r'(\d+)\+?\s*(?:years?|yrs?)',
            r'experience.*?(\d+)\s*(?:years?|yrs?)'
        ]
        
        for pattern in experience_patterns:
            match = re.search(pattern, resume_text.lower())
            if match:
                experience = f"{match.group(1)} years"
                break
        
        # Try to extract education (basic pattern matching)
        education = ""
        education_keywords = [
            "bachelor", "master", "phd", "doctorate", "mba", "computer science", 
            "engineering", "business", "mathematics", "physics", "chemistry"
        ]
        
        for keyword in education_keywords:
            if keyword in resume_text.lower():
                education = keyword.title()
                break
        
        # Create enhanced document for vectorization
        document = {
            "id": str(uuid.uuid4()),
            "type": "resume",
            "fileUrl": file_url,
            "filename": filename,
            "content": resume_text,
            "contentLength": len(resume_text),
            "uploadTimestamp": datetime.utcnow().isoformat(),
            "status": "pending_vectorization",
            "vectorized": False,
            
            # Vector embeddings (to be populated by vectorization process)
            "contentVector": None,  # Will be populated by vectorization service
            "titleVector": None,    # Will be populated by vectorization service
            
            # Search optimization fields
            "searchableText": resume_text.lower(),
            "keywords": keywords,
            "skills": detected_skills,
            "experience": experience,
            "education": education,
            
            # Metadata
            "metadata": {
                "source": "sharepoint_pdf",
                "processingMethod": "pymupdf",
                "version": "1.0",
                "contentType": "application/pdf",
                "vectorModel": "text-embedding-ada-002"
            },
            
            "wordCount": len(words),
            "characterCount": len(resume_text),
            "lineCount": len(lines),
            
            # Additional analytics fields
            "analytics": {
                "skillsCount": len(detected_skills),
                "keywordsCount": len(keywords),
                "avgWordsPerLine": len(words) / len(lines) if lines else 0,
                "readabilityScore": len(words) / len(resume_text.split('.')) if '.' in resume_text else 0
            }
        }
        
        # Upload to Cosmos DB
        result = container.create_item(document)
        
        logging.info(f"Successfully uploaded resume to Cosmos DB with ID: {result['id']}")
        logging.info(f"Detected skills: {detected_skills}")
        logging.info(f"Experience found: {experience}")
        logging.info(f"Education found: {education}")
        
        return result
        
    except CosmosHttpResponseError as e:
        logging.error(f"Cosmos DB error: {str(e)}")
        raise Exception(f"Failed to upload to Cosmos DB: {str(e)}")
    except Exception as e:
        logging.error(f"Error uploading to Cosmos DB: {str(e)}")
        raise Exception(f"Failed to upload to Cosmos DB: {str(e)}") 