import datetime
import io
import json

from django.core.exceptions import ValidationError
from django.db.models import signals
from django.dispatch import receiver
from django.urls import reverse
from django.utils.functional import cached_property
from fernet_fields import EncryptedTextField
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from djtoolbox.db.models import DocumentFileField
from djtoolbox.decorators import cached_method
from djtoolbox.storages import MinioMediaStorage
from djtoolbox.storages.utils import UploadToGenerator
from djtools.db import models
from editais_ppc import querysets
from rh.models import Servidor

MANGAE_OWNER_SCOPE = 'https://www.googleapis.com/auth/drive.file'


class CredentialsError(Exception):
    pass


def check_back_slash(value):
    if value.endswith('/'):
        raise ValidationError('Remove the last "/" from organizational_unit')


class GoogleCloudCredential(models.ModelPlus):
    service_name = models.CharField(verbose_name='Service name', max_length=255, unique=True)
    client_secret = EncryptedTextField(verbose_name='Client Secret', null=True)
    credentials_content = EncryptedTextField(verbose_name='Credentials Content', null=True, blank=True)

    def create_credentials(self):
        flow = InstalledAppFlow.from_client_config(
            json.loads(self.client_secret), [
                MANGAE_OWNER_SCOPE
            ])
        creds = flow.run_console()

        self.credentials_content = json.dumps({
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
        })

    @cached_property
    def credentials(self):
        if not self.credentials_content:
            raise CredentialsError()

        info = json.loads(self.credentials_content)
        credentials = Credentials(**info)

        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                raise CredentialsError()

        return credentials

    @cached_property
    def service(self):
        return build('docs', 'v1', credentials=self.credentials)

    @cached_property
    def service_drive(self):
        return build('drive', 'v3', credentials=self.credentials)


class ArquivoGoogleDocs(models.ModelPlus):
    url = models.URLField(blank=True, verbose_name='Link para o Documento')
    google_id = models.CharField(verbose_name='ID do documento', max_length=1024)

    @cached_property
    def google_cloud(self):
        gcc = GoogleCloudCredential.objects.last()
        return gcc

    def adicionar_permissao(self, email, role):
        self.google_cloud.service_drive.permissions().create(
            fileId=self.google_id, body={'role': role, 'type': 'user', 'emailAddress': email}
        ).execute()

    def atualizar_permissao(self, email, role):
        permissions = self.listar_permissoes()
        for perm in permissions['permissions']:
            if perm['emailAddress'] == email:
                self.google_cloud.service_drive.permissions().update(
                    fileId=self.google_id, permissionId=perm['id'], body={'role': role}
                ).execute()

    def atualizar_permissao_por_id(self, permission_id, role):
        self.google_cloud.service_drive.permissions().update(
            fileId=self.google_id, permissionId=permission_id, body={'role': role}
        ).execute()

    def remover_permissao(self, email):
        permissions = self.listar_permissoes()
        for perm in permissions['permissions']:
            if perm['emailAddress'] == email:
                self.google_cloud.service_drive.permissions().delete(
                    fileId=self.google_id, permissionId=perm['id'],
                ).execute()

    def remover_permissoes(self):
        permissions = self.listar_permissoes()
        for perm in permissions['permissions']:
            if not perm['role'] == 'owner':
                self.google_cloud.service_drive.permissions().delete(
                    fileId=self.google_id, permissionId=perm['id'],
                ).execute()

    def atualizar_permissoes(self, role):
        permissions = self.listar_permissoes()
        for perm in permissions['permissions']:
            if not perm['role'] == 'owner':
                self.google_cloud.service_drive.permissions().update(
                    fileId=self.google_id, permissionId=perm['id'], body={'role': role}
                ).execute()

    @cached_method
    def listar_permissoes(self):
        permissions = self.google_cloud.service_drive.permissions().list(
            fileId=self.google_id, fields='*'
        ).execute()
        return permissions

    def verificar_permissao(self, email, nivel_acesso):
        for permissao in self.listar_permissoes()['permissions']:
            if email == permissao['emailAddress'] and nivel_acesso == permissao['role']:
                return True
        return False

    def clonar(self, nome):
        response = self.google_cloud.service_drive.files().copy(
            fileId=self.google_id, body={'name': nome}
        ).execute()

        return ArquivoGoogleDocs.objects.create(
            google_id=response.get('id'),
            url='https://docs.google.com/document/d/{}'.format(response.get('id'))
        )

    def download(self):
        gc = self.google_cloud
        request = gc.service_drive.files().export_media(
            fileId=self.google_id,
            mimeType='application/pdf'
        )
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return fh.getvalue()

    class Meta:
        verbose_name = u'Arquivo Google Docs'
        verbose_name_plural = u'Arquivos Google Docs'

    def __str__(self):
        return self.google_id


class ModeloPPC(ArquivoGoogleDocs):
    nome = models.CharField(verbose_name='Nome', max_length=255, unique=True)

    class Meta:
        verbose_name = u'Modelo de PPC'
        verbose_name_plural = u'Modelos de PPCs'

    def __str__(self):
        return self.nome


class Documento(models.ModelPlus):
    nome = models.CharField('Nome do documento', max_length=255, unique=True)
    url = models.URLField(verbose_name='URL', blank=True, null=True)
    arquivo = DocumentFileField(
        verbose_name='Arquivo',
        size=2,
        format=['pdf', 'doc', 'docx'],
        blank=True,
        null=True,
        upload_to=UploadToGenerator(['editais_ppc', 'documentos']),
        storage=MinioMediaStorage()
    )

    class Meta:
        verbose_name = u'Documento'
        verbose_name_plural = u'Documentos'

    def __str__(self):
        return self.nome


class TipoEdital(models.ModelPlus):
    nome = models.CharField('Nome', max_length=255, unique=True)

    class Meta:
        verbose_name = u'Tipo do Edital'
        verbose_name_plural = u'Tipos de Editais'

    def __str__(self):
        return self.nome


class Edital(models.ModelPlus):
    nome = models.CharField(verbose_name='Nome', max_length=1024)
    numero = models.PositiveIntegerField(verbose_name='Número do edital')
    ano = models.PositiveIntegerField(verbose_name='Ano')
    tipo = models.ForeignKey(
        TipoEdital,
        verbose_name='Tipo do Edital',
        related_name='editais',
        on_delete=models.PROTECT
    )
    quantidade_avaliadores = models.PositiveIntegerField(
        verbose_name='Quantidade de avaliadores',
        help_text='Quantidade de avaliadores por PPC'
    )
    avaliadores = models.ManyToManyFieldPlus(
        'rh.Servidor',
        related_name='editais_ppc'
    )
    arquivo = DocumentFileField(
        verbose_name='Arquivo do Edital',
        size=2,
        format=['pdf'],
        upload_to=UploadToGenerator(['editais_ppc', 'editais']),
        storage=MinioMediaStorage()
    )
    documentos = models.ManyToManyFieldPlus(
        Documento,
        verbose_name='Documentos',
        related_name='editais',
        blank=True
    )
    modelo_ppc = models.ForeignKey(
        ModeloPPC,
        verbose_name='Modelo PPC',
        related_name='editais',
        on_delete=models.PROTECT
    )
    inicio_inscricao = models.DateFieldPlus(
        verbose_name='Data inicial para a inscrição no edital'
    )
    fim_inscricao = models.DateFieldPlus(
        verbose_name='Data final para a inscrição no edital'
    )
    inicio_analise = models.DateFieldPlus(
        verbose_name='Data inicial para a análise dos PPCs'
    )
    fim_analise = models.DateFieldPlus(
        verbose_name='Data final para a análise dos PPCs'
    )
    inicio_ajuste = models.DateFieldPlus(
        verbose_name='Data inicial para ajustes nos PPCs'
    )
    fim_ajuste = models.DateFieldPlus(
        verbose_name='Data final para ajustes nos PPCs'
    )
    data_resultado = models.DateFieldPlus(
        verbose_name='Data final para o resultado nos PPCs'
    )

    objects = querysets.EditalQuerySet.as_manager()

    def get_absolute_url(self):
        return reverse('editais_ppc:edital_ppc', args=[self.pk])

    def em_periodo_inscricao(self):
        today = datetime.date.today()
        return self.inicio_inscricao <= today <= self.fim_inscricao

    def em_periodo_analise(self):
        today = datetime.date.today()
        return self.inicio_analise <= today <= self.fim_analise

    def em_periodo_ajuste(self):
        today = datetime.date.today()
        return self.inicio_ajuste <= today <= self.fim_ajuste

    def em_periodo_pre_ajuste(self):
        today = datetime.date.today()
        return self.fim_analise < today < self.inicio_ajuste

    def em_periodo_pos_ajuste(self):
        today = datetime.date.today()
        return self.fim_ajuste < today

    def em_data_resultado(self):
        today = datetime.date.today()
        return self.data_resultado == today

    class Meta:
        verbose_name = u'Edital'
        verbose_name_plural = u'Editais'

    def __str__(self):
        return '{self.nome} - {self.numero}/{self.ano}'.format(self=self)


class Inscricao(models.ModelPlus):
    edital = models.ForeignKey(
        Edital,
        verbose_name='Edital',
        related_name='inscricoes',
        on_delete=models.PROTECT
    )
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    portaria = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        verbose_name='Portaria',
        related_name='inscricoes_ppc',
        on_delete=models.PROTECT
    )
    membros = models.ManyToManyFieldPlus(
        Servidor,
        verbose_name='Membros',
        related_name='inscricoes_ppc',
    )

    ppc = models.ForeignKey(
        ArquivoGoogleDocs,
        verbose_name='PPC',
        related_name='inscricoes',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = u'Inscrição'
        verbose_name_plural = u'Inscrições'

    def clean(self):
        super(Inscricao, self).clean()

        if self.edital and not self.edital.em_periodo_inscricao():
            raise ValidationError({'edital': 'Fora do período de inscrição'})

    def submeter(self, user):
        Submissao.objects.create(
            inscricao=self,
            usuario=user.get_servidor()
        )

    @property
    def is_submetida(self):
        return Submissao.objects.filter(inscricao=self).exists()

    def __str__(self):
        return 'Comissão #{self.portaria_id} em {self.edital}'.format(self=self)

    def save(self, *args, **kargs):
        if not self.ppc:
            self.ppc = self.edital.modelo_ppc.clonar(self.edital.modelo_ppc.nome)
        super(Inscricao, self).save(*args, **kargs)


@receiver(signals.m2m_changed, sender=Inscricao.membros.through)
def set_perms_for_membros(sender, instance, action, **kargs):
    inscricao = instance
    if action == 'post_add' and inscricao.edital.em_periodo_inscricao():
        membros = inscricao.membros.all()
        for membro in membros:
            inscricao.ppc.adicionar_permissao(membro.email_institucional, 'writer')


class Submissao(models.ModelPlus):
    data = models.DateTimeField(verbose_name='Data', auto_now_add=True)
    usuario = models.ForeignKey(
        'rh.Servidor',
        verbose_name='Usuário',
        related_name='submissoes_ppc',
        on_delete=models.PROTECT
    )
    inscricao = models.OneToOneField(
        Inscricao,
        verbose_name='Inscrição',
        related_name='submissao',
        on_delete=models.PROTECT
    )
    avaliadores = models.ManyToManyFieldPlus(
        'rh.Servidor',
        verbose_name='Avaliadores',
        related_name='avaliadores_ppc',
        blank=True
    )

    objects = querysets.SubmissaoQuerySet.as_manager()

    class Meta:
        verbose_name = u'Submissão'
        verbose_name_plural = u'Submissões'

    def __str__(self):
        return 'Submissão {}'.format(self.id)

    @classmethod
    def periodo_analise_perms(cls):
        submissoes = Submissao.objects.all()
        for submissao in submissoes:
            if submissao.inscricao.edital.em_periodo_analise():
                for avaliador in submissao.avaliadores.all():
                    if not submissao.inscricao.ppc.verificar_permissao(avaliador.email_institucional, 'writer'):
                        submissao.inscricao.ppc.adicionar_permissao(avaliador.email_institucional, 'writer')
            elif submissao.inscricao.edital.em_periodo_pre_ajuste():
                submissao.inscricao.ppc.atualizar_permissoes('commenter')

    @classmethod
    def periodo_ajuste_perms(cls):
        submissoes = Submissao.objects.filter(avaliacoes__situacao__impeditiva=False)
        for submissao in submissoes:
            if submissao.inscricao.edital.em_periodo_ajuste():
                for membro_inscricao in submissao.inscricao.membros.all():
                    email = membro_inscricao.email_institucional
                    submissao.inscricao.ppc.atualizar_permissao(email, 'writer')
                for avaliador in submissao.inscricao.submissao.avaliadores.all():
                    email = avaliador.email_institucional
                    submissao.inscricao.ppc.atualizar_permissao(email, 'commenter')
            if submissao.inscricao.edital.em_periodo_pos_ajuste:
                submissao.inscricao.ppc.atualizar_permissoes('commenter')


@receiver(signals.post_save, sender=Submissao)
def submissao_perms(sender, created, instance, **kwargs):
    submissao = instance
    if created and submissao.inscricao.edital.em_periodo_inscricao():
        for membro_inscricao in submissao.inscricao.membros.all():
            email = membro_inscricao.email_institucional
            submissao.inscricao.ppc.atualizar_permissao(email, 'reader')


class SituacaoPPC(models.ModelPlus):
    nome = models.CharField(verbose_name='Nome', max_length=50, unique=True)
    impeditiva = models.BooleanField(
        verbose_name='Impeditiva',
        default=False,
        blank=True
    )
    ativa = models.BooleanField(
        verbose_name='Ativa',
        default=True,
        blank=True
    )

    class Meta:
        verbose_name = u'Situação no PPC'
        verbose_name_plural = u'Situações dos PPCs'

    def __str__(self):
        return self.nome


class Resultado(models.ModelPlus):
    data = models.DateTimeField(verbose_name='Data', auto_now_add=True)
    situacao = models.ForeignKey(
        SituacaoPPC,
        verbose_name='Situação',
        related_name='resultados',
        on_delete=models.PROTECT
    )
    submissao = models.OneToOneField(
        Submissao,
        verbose_name='Submissão',
        related_name='resultado',
        on_delete=models.PROTECT
    )

    class Meta:
        verbose_name = u'Resultado'
        verbose_name_plural = u'Resultados'

    def __str__(self):
        return '{self.submissao} - {self.situacao}'.format(self=self)


class Avaliacao(models.ModelPlus):
    avaliador = models.ForeignKey(
        'rh.Servidor',
        verbose_name='Avaliador',
        related_name='avaliacoes',
        on_delete=models.PROTECT
    )
    submissao = models.ForeignKey(
        Submissao,
        verbose_name='Submissão',
        related_name='avaliacoes',
        on_delete=models.PROTECT
    )
    cadastrada_em = models.DateTimeField(verbose_name='Data da avaliação', auto_now_add=True)
    situacao = models.ForeignKey(
        SituacaoPPC,
        verbose_name='Situação',
        related_name='avaliacoes',
        on_delete=models.PROTECT,
        blank=False
    )
    justificativa = models.TextField(verbose_name='Justificativa', blank=True)

    objects = querysets.AvaliacaoQuerySet.as_manager()

    class Meta:
        verbose_name = u'Avaliação'
        verbose_name_plural = u'Avaliações'
        unique_together = ['avaliador', 'submissao']

    def __str__(self):
        return '{self.avaliador} - {self.submissao}'.format(self=self)


class SolicitacaoCorrecao(models.ModelPlus):
    ADICAO = 1
    ALTERACAO = 2
    EXCLUSAO = 3
    TIPO_CHOICES = (
        (ADICAO, 'Adição'),
        (ALTERACAO, 'Alteração'),
        (EXCLUSAO, 'Exclusão')
    )
    cadastrada_em = models.DateTimeField(verbose_name='Data', auto_now_add=True)
    avaliacao = models.ForeignKey(
        Avaliacao,
        verbose_name='Avaliação',
        related_name='solicitacoes',
        on_delete=models.CASCADE
    )
    tipo = models.PositiveSmallIntegerField(verbose_name='Tipo de Solicitação', choices=TIPO_CHOICES)
    comentario = models.TextField(verbose_name='Comentário')

    def __str__(self):
        return '{self.avaliacao.avaliador} - {self.tipo} - {self.data}'.format(self=self)

    class Meta:
        verbose_name = u'Solicitação Correção'
        verbose_name_plural = u'Solicitação Correções'

    def is_adicao(self):
        return self.tipo == self.ADICAO

    def is_alteracao(self):
        return self.tipo == self.ALTERACAO

    def is_exclusao(self):
        return self.tipo == self.EXCLUSAO

    def tipo_css_class(self):
        classes = {
            self.ADICAO: 'success',
            self.ALTERACAO: 'alert',
            self.EXCLUSAO: 'error',
        }
        return classes.get(self.tipo)
