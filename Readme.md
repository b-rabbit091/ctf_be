#  CTF Backend

This is the **backend service** for the Capture The Flag (CTF) platform.
It’s built with **Django + Django REST Framework**, using **PostgreSQL** as the database.

---
##  Installation and Setup

Follow the steps below to install dependencies and run the project in your local environment.
Default username : admin
Default password : password

---

##  Python requirement

Please ensure you have the following installed:

-`python:3.11`

---

### 1. Clone the Repository
Active branch : v1.0
```bash
git clone git@github.com:b-rabbit091/ctf_be.git
cd ctf_be
```

### 2. Environment variables
Create a `.env` file inside the `ctf_be/` directory. Replace with corresponding values.

```
DEBUG=1
SECRET_KEY=replace_me
DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1 [::1]
POSTGRES_DB=ctf_db
POSTGRES_USER=django_user
POSTGRES_PASSWORD=password
POSTGRES_HOST=db
POSTGRES_PORT=5432
EMAIL_HOST_PASSWORD=hostpassword
EMAIL_HOST_USER='user@email.com'

```

### 3.Running Locally

a . Create a virutal env
```bash 
    python -m venv venv 
```

b . Active virtual env in Linux, macOS as
``` bash 
       source venv/bin/active
```
OR in windows as
```
./venv/Scripts/activate 
```

c. Install dependencies
```bash
pip install -r requirements.txt
````

d. Run migrations
```bash 
python manage.py migrate
````

e. Start the server
```bash
python manage.py runserver
```

f. Then visit:

```
http://127.0.0.1:8000/
```

---

### 4. API Documentation (Swagger)

Swagger api documentation :

```
http://localhost:8000/swagger/
```


