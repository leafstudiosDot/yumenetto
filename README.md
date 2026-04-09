# YumeNetto

This is a YumeNetto server implementation built with Django. The community platform that users can join anonymously, create threads, and interact within the specified community.

## Software Requirements
- Python 3.8+
- pip
- (Optional) Docker & Docker Compose

## Setup Instructions

### 1. Clone the Repository
```bash
git clone <repository-url>
cd yumenetto_server
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Apply Migrations
```bash
python manage.py migrate
```

### 5. Create a Superuser (Admin)
```bash
python manage.py createsuperuser
```

### 6. Run the Development Server
```bash
python manage.py runserver
```

The server will be available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## Docker

To run YumeNetto using Docker:
```bash
docker-compose up --build
```

## Admin
Access the Django admin at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

© leafstudiosDot 2026. All rights reserved.