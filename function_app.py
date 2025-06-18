import azure.functions as func
import base64
import pymupdf
import logging

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="ingestresume",methods=["POST"])
def ingestresume(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    try:
        # Get the request body
        req_body = req.get_body()
        
        # Decode base64 PDF
        pdf_bytes = base64.b64decode(req_body)
        
        doc = pymupdf.Document(stream=pdf_bytes, filetype="pdf") # Open the PDF file

        # Initialize text variable to store all extracted text
        extracted_text = ""
        
        # Iterate through pages and extract text
        for page in doc:
            text = page.get_text()  # get plain text
            extracted_text += text + "\n"  # add page text with newline separator
        
        return func.HttpResponse(
            extracted_text,
            mimetype="text/plain",
            status_code=200
        )
        
    except Exception as e:
        logging.error(f"Error processing PDF: {str(e)}")
        return func.HttpResponse(
            f"Error processing PDF: {str(e)}",
            status_code=400
        ) 