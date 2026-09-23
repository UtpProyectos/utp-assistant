FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# La base de datos se guarda en /data para poder montarla como volumen
ENV CRM_DB=/data/crm.db
RUN mkdir -p /data

EXPOSE 5000
CMD ["python", "app.py"]
