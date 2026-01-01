# SmartCampus Production Deployment Guide

This guide covers deploying SmartCampus to a production server with Nginx, Gunicorn, and proper security configurations.

## Prerequisites

- Ubuntu 20.04+ or similar Linux distribution
- Python 3.8+
- MySQL 5.7+ or MySQL 8.0+
- Nginx
- Redis (for caching)
- SSL certificate (Let's Encrypt recommended)

## Step 1: Server Setup

### 1.1 Update System Packages
```bash
sudo apt update
sudo apt upgrade -y
```

### 1.2 Install Required Packages
```bash
sudo apt install -y python3-pip python3-venv python3-dev
sudo apt install -y mysql-server mysql-client
sudo apt install -y nginx redis-server
sudo apt install -y build-essential libssl-dev libffi-dev
sudo apt install -y libmysqlclient-dev
```

### 1.3 Install SSL Certificate (Let's Encrypt)
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

## Step 2: Database Setup

### 2.1 Create Database and User
```bash
sudo mysql -u root -p
```

In MySQL:
```sql
CREATE DATABASE smartcampus CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'smartcampus_user'@'localhost' IDENTIFIED BY 'your-secure-password';
GRANT ALL PRIVILEGES ON smartcampus.* TO 'smartcampus_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

## Step 3: Application Setup

### 3.1 Create Application User
```bash
sudo adduser --system --group --home /var/www/smartcampus smartcampus
```

### 3.2 Clone/Upload Application
```bash
sudo mkdir -p /var/www/smartcampus
sudo chown smartcampus:smartcampus /var/www/smartcampus
cd /var/www/smartcampus
# Upload your application files here
```

### 3.3 Create Virtual Environment
```bash
cd /var/www/smartcampus
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3.4 Configure Environment Variables
```bash
cp env.example .env
nano .env  # Edit with your actual values
```

**Important:** Generate a new SECRET_KEY:
```bash
python manage.py shell
>>> from django.core.management.utils import get_random_secret_key
>>> print(get_random_secret_key())
```

### 3.5 Run Migrations
```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

### 3.6 Create Required Directories
```bash
sudo mkdir -p /var/log/smartcampus
sudo mkdir -p /var/log/gunicorn
sudo mkdir -p /var/run/gunicorn
sudo chown -R smartcampus:smartcampus /var/log/smartcampus
sudo chown -R smartcampus:smartcampus /var/log/gunicorn
sudo chown -R smartcampus:smartcampus /var/run/gunicorn
```

## Step 4: Gunicorn Setup

### 4.1 Create Gunicorn Systemd Service
Create `/etc/systemd/system/smartcampus.service`:

```ini
[Unit]
Description=SmartCampus Gunicorn daemon
After=network.target

[Service]
User=smartcampus
Group=smartcampus
WorkingDirectory=/var/www/smartcampus
Environment="PATH=/var/www/smartcampus/venv/bin"
ExecStart=/var/www/smartcampus/venv/bin/gunicorn \
    --config /var/www/smartcampus/gunicorn_config.py \
    smartcampus.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 4.2 Update Gunicorn Config
Edit `gunicorn_config.py` and update paths:
- `bind = "unix:/var/run/gunicorn/smartcampus.sock"`
- `user = "smartcampus"`
- `group = "smartcampus"`

### 4.3 Start Gunicorn Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable smartcampus
sudo systemctl start smartcampus
sudo systemctl status smartcampus
```

## Step 5: Nginx Setup

### 5.1 Configure Nginx
Edit `nginx.conf` and update:
- `server_name` with your domain
- SSL certificate paths
- Static and media file paths

### 5.2 Install Nginx Configuration
```bash
sudo cp nginx.conf /etc/nginx/sites-available/smartcampus
sudo ln -s /etc/nginx/sites-available/smartcampus /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default  # Remove default site if needed
```

### 5.3 Test and Reload Nginx
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Step 6: Redis Setup

### 6.1 Configure Redis
Edit `/etc/redis/redis.conf`:
```
bind 127.0.0.1
requirepass your-redis-password  # Optional but recommended
```

### 6.2 Start Redis
```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

Update your `.env` file with Redis password if set:
```
REDIS_URL=redis://:your-redis-password@127.0.0.1:6379/1
```

## Step 7: Firewall Configuration

```bash
sudo ufw allow 'Nginx Full'
sudo ufw allow OpenSSH
sudo ufw enable
```

## Step 8: Production Settings

### 8.1 Update WSGI to Use Production Settings
Edit `/var/www/smartcampus/smartcampus/wsgi.py`:
```python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartcampus.settings_production')
```

Or set environment variable in systemd service:
```ini
Environment="DJANGO_SETTINGS_MODULE=smartcampus.settings_production"
```

### 8.2 Verify Production Settings
- DEBUG = False
- SECRET_KEY from environment
- All security headers enabled
- SSL redirect enabled

## Step 9: Monitoring and Maintenance

### 9.1 View Logs
```bash
# Application logs
sudo tail -f /var/log/smartcampus/django.log

# Gunicorn logs
sudo tail -f /var/log/gunicorn/smartcampus_error.log

# Nginx logs
sudo tail -f /var/log/nginx/smartcampus_error.log
```

### 9.2 Restart Services
```bash
sudo systemctl restart smartcampus
sudo systemctl restart nginx
```

### 9.3 Update Application
```bash
cd /var/www/smartcampus
source venv/bin/activate
git pull  # If using git
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart smartcampus
```

## Security Checklist

- [ ] DEBUG = False
- [ ] SECRET_KEY from environment variable
- [ ] Database password not in code
- [ ] SSL certificate installed and auto-renewal configured
- [ ] Firewall configured
- [ ] Regular backups configured
- [ ] Log rotation configured
- [ ] Strong database passwords
- [ ] Application runs as non-root user
- [ ] File permissions set correctly

## Troubleshooting

### Gunicorn won't start
- Check logs: `sudo journalctl -u smartcampus -n 50`
- Verify socket permissions
- Check Python path in systemd service

### Nginx 502 Bad Gateway
- Check Gunicorn is running: `sudo systemctl status smartcampus`
- Verify socket file exists: `ls -la /var/run/gunicorn/smartcampus.sock`
- Check socket permissions

### Static files not loading
- Run `python manage.py collectstatic`
- Verify STATIC_ROOT path in settings
- Check Nginx static file location matches STATIC_ROOT

### Database connection errors
- Verify database credentials in .env
- Check MySQL is running: `sudo systemctl status mysql`
- Test connection: `mysql -u smartcampus_user -p smartcampus`

## Backup Strategy

### Database Backup
```bash
# Daily backup script
mysqldump -u smartcampus_user -p smartcampus > /backup/smartcampus_$(date +%Y%m%d).sql
```

### Media Files Backup
```bash
tar -czf /backup/media_$(date +%Y%m%d).tar.gz /var/www/smartcampus/media/
```

## Performance Optimization

1. Enable Redis caching (already configured)
2. Use CDN for static files (optional)
3. Enable database query caching
4. Configure Nginx caching for static assets
5. Use Gunicorn with multiple workers (already configured)

## Support

For issues, check:
- Application logs: `/var/log/smartcampus/`
- Gunicorn logs: `/var/log/gunicorn/`
- Nginx logs: `/var/log/nginx/`
- System logs: `sudo journalctl -u smartcampus`

