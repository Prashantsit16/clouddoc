# CloudDoc ☁️📄

CloudDoc is a highly scalable, cloud-native document processing platform. It allows users to securely upload PDF documents directly to Amazon S3, processes them asynchronously using an event-driven worker architecture, and extracts their textual content using a modern React frontend.

![CloudDoc Architecture](https://img.shields.io/badge/Architecture-Cloud--Native-blue.svg)
![React](https://img.shields.io/badge/Frontend-React-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)
![AWS](https://img.shields.io/badge/Cloud-AWS-232F3E?logo=amazon-aws)

---

## 🌟 Key Features
- **Secure Authentication**: JWT-based login and registration.
- **Direct-to-S3 Uploads**: The frontend securely retrieves presigned upload URLs from the backend and performs HTTP PUT uploads directly to S3, saving backend bandwidth.
- **Event-Driven Processing**: 
  - Amazon S3 `ObjectCreated` events trigger an SQS message.
  - A detached Python background worker continuously polls SQS.
- **Background PDF Extraction**: The worker securely downloads the PDF using an IAM instance profile, extracts text using `PyMuPDF`, and updates the central PostgreSQL database.
- **Automated CI/CD**: Fully integrated GitHub Actions workflow for building Docker containers, pushing to Amazon ECR, and executing zero-downtime deployments to EC2 via AWS Systems Manager (SSM).

## 🏗️ Architecture Stack
* **Frontend**: React, Vite, TypeScript, Nginx
* **Backend API**: Python, FastAPI, SQLAlchemy, Pydantic, Uvicorn
* **Database**: PostgreSQL (via Psycopg)
* **Worker**: Python, Boto3, PyMuPDF, SQS
* **Cloud Infrastructure**: AWS EC2 (Amazon Linux 2023), AWS S3, AWS SQS, AWS ECR, AWS Systems Manager (SSM)
* **Containerization**: Docker & Docker Compose

## 🚀 Local Development Setup

To run CloudDoc locally for development:

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Prashantsit16/clouddoc.git
   cd clouddoc
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   # Database Configuration
   DATABASE_URL=postgresql+psycopg://postgres:prashant@db:5432/clouddoc
   
   # JWT Configuration
   JWT_SECRET_KEY=YourSuperSecretKeyHere
   JWT_ALGORITHM=HS256
   JWT_EXPIRE_MINUTES=1440
   
   # AWS Configuration
   AWS_REGION=us-east-1
   AWS_S3_BUCKET=your-s3-bucket-name
   AWS_SQS_QUEUE_NAME=your-sqs-queue-name
   ```

3. **Start the Stack using Docker Compose**:
   ```bash
   docker-compose up --build
   ```

4. **Run Database Migrations**:
   *(In a new terminal window)*
   ```bash
   docker-compose exec backend python scratch/alter_db.py
   ```

5. **Access the Application**:
   - Frontend Dashboard: `http://localhost:5173`
   - Backend API Docs: `http://localhost:8000/docs`

## ☁️ Production Deployment

The application is configured for an automated deployment pipeline utilizing GitHub Actions and AWS.

### CI/CD Workflow (`ci-cd.yml`)
1. **GitHub OIDC**: Connects securely to AWS without storing long-lived access keys.
2. **Build & Push**: Builds the `backend` and `frontend` Docker images and pushes them to Amazon Elastic Container Registry (ECR).
3. **SSM Deployment**: Uses AWS Systems Manager (`ssm:SendCommand`) to execute a script on the target EC2 instance. This script pulls the newly pushed Docker images from ECR and restarts the `docker-compose` services.

### EC2 Production Environment
- **Web Server**: The React frontend is served as a static bundle using a lightweight `nginx:alpine` container. Nginx acts as a reverse proxy, smoothly routing `/auth` and `/documents` API requests directly to the FastAPI container without exposing the backend port to the open internet.
- **IAM Security**: The EC2 instance assumes an IAM Instance Profile (`CloudDoc-EC2-Profile`), granting the background worker and the SSM agent direct access to S3, SQS, and ECR without needing any `.env` AWS keys.

## 🤝 Contributing
Feel free to open issues or submit pull requests for any bugs or improvements!

## 📜 License
This project is licensed under the MIT License.
