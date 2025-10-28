

#  CTF Backend

This is the **backend service** for the Capture The Flag (CTF) platform.
It’s built with **Django + Django REST Framework**, using **PostgreSQL** as the database.


---

##  Environment Setup

Create a `.env` file in the `ctf_backend/` directory (if not already present):

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


## 🧪 Running Locally (Without Docker)

If you prefer to run it manually:

```
# Install python version python:3.11

# Create a virutal env
    python -m venv venv 

# Active virtual env
    source venv/bin/active (Linux,mac)
    ./venv/bin/activate (windows)

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start the server
python manage.py runserver
```

Then visit:

```
http://127.0.0.1:8000/
```

---

## 🧾 API Documentation (Swagger)

If Swagger is enabled, visit:

```
http://localhost:8000/swagger/
```
