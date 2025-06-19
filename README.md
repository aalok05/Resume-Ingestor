# Resume Ingestor Azure Function

A serverless Azure Function that extracts text from PDF resumes, processes them using Azure OpenAI for intelligent data extraction, and stores structured candidate information in Azure Cosmos DB for text-based search and retrieval.

## 🏗️ Architecture

```
PDF Upload → Azure Function → AI Processing (Azure OpenAI) → Cosmos DB Storage
```

## ✨ Features

- **PDF Text Extraction**: Uses PyMuPDF to extract text from PDF resumes
- **AI-Powered Data Extraction**: Leverages Azure OpenAI GPT-4o to extract:
  - Personal information (name, email, location)
  - Technical skills with proficiency levels and experience years
  - Soft skills
  - Work experience and current role
  - Industry experience
  - Certifications
- **Flexible Tagging**: Support for custom tags (external, senior, remote, etc.)
- **Searchable Text Generation**: Automatically creates optimized search text
- **Cosmos DB Integration**: Stores structured data for efficient querying

## 📋 Prerequisites

- Azure Subscription
- Azure Functions Core Tools 4.x
- Python 3.9+
- Azure Cosmos DB account
- Azure OpenAI resource with GPT-4o deployment

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd ResumeIngestor/Resume-Ingestor
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `local.settings.json.template` to `local.settings.json` and update the values:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "COSMOS_ENDPOINT": "https://your-cosmos-account.documents.azure.com:443/",
    "COSMOS_KEY": "your-cosmos-primary-key",
    "COSMOS_DATABASE_NAME": "exploredb",
    "COSMOS_CONTAINER_NAME": "resumes",
    "AZURE_OPENAI_ENDPOINT": "https://your-openai-resource.cognitiveservices.azure.com/openai/deployments/gpt-4o/chat/completions?api-version=2025-01-01-preview",
    "AZURE_OPENAI_KEY": "your-azure-openai-key",
    "AZURE_OPENAI_DEPLOYMENT_NAME": "gpt-4o",
    "AZURE_OPENAI_API_VERSION": "2024-12-01-preview"
  }
}
```

## 🔧 Environment Variables Configuration

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `COSMOS_ENDPOINT` | Cosmos DB account endpoint | `https://mydb.documents.azure.com:443/` |
| `COSMOS_KEY` | Cosmos DB primary key | `ABC123...` |
| `COSMOS_DATABASE_NAME` | Database name | `exploredb` |
| `COSMOS_CONTAINER_NAME` | Container name | `resumes` |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | `https://myai.cognitiveservices.azure.com/...` |
| `AZURE_OPENAI_KEY` | Azure OpenAI API key | `XYZ789...` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | GPT deployment name | `gpt-4o` |
| `AZURE_OPENAI_API_VERSION` | API version | `2024-12-01-preview` |

### Getting Environment Values

#### Cosmos DB
1. Go to Azure Portal → Cosmos DB account
2. **Keys** section:
   - `COSMOS_ENDPOINT`: Copy "URI"
   - `COSMOS_KEY`: Copy "Primary Key"

#### Azure OpenAI
1. Go to Azure Portal → Azure OpenAI resource
2. **Keys and Endpoint** section:
   - `AZURE_OPENAI_KEY`: Copy "Key 1"
   - `AZURE_OPENAI_ENDPOINT`: Copy "Endpoint"
3. **Model deployments** section:
   - `AZURE_OPENAI_DEPLOYMENT_NAME`: Your GPT-4o deployment name

## 🗄️ Cosmos DB Setup

### 1. Create Database and Container

```bash
# Using Azure CLI
az cosmosdb sql database create --account-name <cosmos-account> --resource-group <rg> --name exploredb
az cosmosdb sql container create --account-name <cosmos-account> --resource-group <rg> --database-name exploredb --name resumes --partition-key-path "/partition_key"
```

### 2. Container Configuration

- **Partition Key**: `/partition_key`
- **Throughput**: 400 RU/s (minimum)
- **Indexing Policy**: Default (all paths indexed for text search)

## 📡 API Usage

### Endpoint
```
POST https://your-function-app.azurewebsites.net/api/ingestresume
```

### Request Format
```json
{
  "FileUrl": "https://sharepoint.com/path/to/resume.pdf",
  "FileContent": "base64-encoded-pdf-content",
  "Tags": "external,senior,fullstack,remote"
}
```

### Response Format
```json
{
  "status": "success",
  "file_url": "https://sharepoint.com/path/to/resume.pdf",
  "tags": "external,senior,fullstack,remote",
  "extracted_text_length": 3000,
  "cosmos_document_id": "abc-123-def-456",
  "candidate_info": {
    "name": "John Doe",
    "email": "john.doe@email.com",
    "location": "San Francisco, CA",
    "total_experience_years": 5,
    "current_role": "Senior Software Engineer",
    "technical_skills_count": 8,
    "soft_skills_count": 5,
    "certifications_count": 2,
    "industries": ["Technology", "Fintech"]
  },
  "message": "Resume processed and uploaded to Cosmos DB successfully"
}
```

## 📄 Document Schema

Documents stored in Cosmos DB follow this structure:

```json
{
  "id": "unique-uuid",
  "partition_key": "active",
  "tags": "external,senior,fullstack",
  "personalInfo": {
    "name": "John Doe",
    "email": "john.doe@email.com",
    "location": "San Francisco, CA"
  },
  "skills": {
    "technical_skills": [
      {
        "skill": "Python",
        "proficiency": "Expert",
        "years": 5
      }
    ],
    "soft_skills": ["Leadership", "Communication", "Problem Solving"]
  },
  "experience": {
    "total_years": 5,
    "current_role": "Senior Software Engineer",
    "industries": ["Technology", "Fintech"]
  },
  "certifications": ["AWS Certified Solutions Architect"],
  "searchable_text": "john doe python senior software engineer leadership technology",
  "metadata": {
    "fileUrl": "https://sharepoint.com/...",
    "filename": "john_doe_resume.pdf",
    "uploadTimestamp": "2025-01-18T10:30:00Z",
    "contentLength": 3000,
    "aiProcessed": true
  }
}
```

## 🔍 Querying Data

### Basic Queries

```sql
-- Find all external candidates
SELECT * FROM c WHERE CONTAINS(c.tags, "external")

-- Search by skills
SELECT * FROM c WHERE CONTAINS(c.searchable_text, "python react")

-- Find senior candidates with specific experience
SELECT * FROM c 
WHERE c.experience.total_years >= 5 
AND CONTAINS(c.searchable_text, "senior")

-- Search by industry
SELECT * FROM c 
WHERE ARRAY_CONTAINS(c.experience.industries, "Technology")

-- Find candidates with certifications
SELECT * FROM c WHERE ARRAY_LENGTH(c.certifications) > 0
```

### Advanced Queries

```sql
-- Multi-criteria search
SELECT c.personalInfo.name, c.experience.current_role, c.skills.technical_skills
FROM c 
WHERE CONTAINS(c.searchable_text, "python javascript") 
AND c.experience.total_years >= 3
AND CONTAINS(c.tags, "remote")

-- Skill proficiency search
SELECT * FROM c 
JOIN skill IN c.skills.technical_skills
WHERE skill.skill = "Python" AND skill.proficiency = "Expert"
```

## 🚀 Deployment

### Local Development

```bash
# Start local development server
func start

# Test endpoint
curl -X POST http://localhost:7071/api/ingestresume \
  -H "Content-Type: application/json" \
  -d @test-payload.json
```

### Deploy to Azure

```bash
# Login to Azure
az login

# Deploy function
func azure functionapp publish <your-function-app-name>

# Set environment variables in Azure
az functionapp config appsettings set \
  --name <your-function-app-name> \
  --resource-group <your-rg> \
  --settings \
  COSMOS_ENDPOINT="https://your-cosmos.documents.azure.com:443/" \
  COSMOS_KEY="your-key" \
  # ... other variables
```

## 🧪 Testing

### Sample Test Payload

Create `test-payload.json`:

```json
{
  "FileUrl": "https://example.com/resume.pdf",
  "FileContent": "JVBERi0xLjQKJdPr6eEKMSAwIG9iago8PAovVHlwZSAvQ2F0YWxvZwovT3V0bGluZXMgMiAwIFIKL1BhZ2VzIDMgMCBSCj4+CmVuZG9iago...",
  "Tags": "test,external,senior"
}
```

### PowerShell Test

```powershell
$body = @{
    FileUrl = "https://example.com/resume.pdf"
    FileContent = "base64-encoded-content"
    Tags = "test,external"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:7071/api/ingestresume" -Method POST -Body $body -ContentType "application/json"
```

## 🔧 Troubleshooting

### Common Issues

#### 1. "Cosmos DB connection settings not found"
- Check environment variables are set correctly
- Verify Cosmos DB account is accessible
- Check firewall settings

#### 2. "Azure OpenAI connection settings not found"
- Verify Azure OpenAI resource is deployed
- Check API key and endpoint
- Ensure GPT-4o model is deployed

#### 3. "Failed to parse AI response as JSON"
- Check Azure OpenAI quota and limits
- Verify deployment name matches
- Review function logs for AI response details

#### 4. PDF processing errors
- Ensure FileContent is valid base64
- Check PDF file is not corrupted
- Verify PDF is not password protected



## 📞 Support

For issues and questions:
- Create an issue in this repository
