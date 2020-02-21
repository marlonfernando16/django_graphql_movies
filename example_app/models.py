from celery import shared_task; from django.db import models
class ModeloPPC(models.Model):
    pass


@shared_task(ignore_result=True)
def criar_documento(id_google_cloud):
    google_docs = ModeloPPC.objects.get(id=id_google_cloud)
    response = google_docs.google_cloud.service.documents().create(body={'title': google_docs.nome}).execute()
    google_docs.google_id = response.get('documentId')
    google_docs.url = 'https://docs.google.com/document/d/{}'.format(response.get('documentId'))
    google_docs.save()
