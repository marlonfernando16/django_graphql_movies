import datetime

import mock
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from faker import Faker
from google.oauth2.credentials import Credentials
from model_mommy import mommy

from djtoolbox.tests import SuapTestCase, Group
from editais_ppc import models, forms
from expedicao.utils import proximo_dia
from rh.tests import recipes as rh_recipes

fake = Faker(locale=settings.LANGUAGE_CODE)

credentials_mock = mock.MagicMock(spec=Credentials)
google_cloud_mock = mock.MagicMock(spec=models.GoogleCloudCredential)
google_cloud_mock.credentials = credentials_mock


def modelo_ppc_make():
    modelo_ppc = mommy.make(
        models.ModeloPPC,
        nome=fake.word(),
        url=fake.uri(),
    )
    modelo_ppc.google_cloud = google_cloud_mock
    modelo_ppc.criar_documento = mock.MagicMock()
    modelo_ppc.criar_documento()
    return modelo_ppc


class EditalFormTestCase(TestCase):

    def setUp(self):
        super(EditalFormTestCase, self).setUp()

    def test_criar_documento(self):
        modelo = modelo_ppc_make()
        self.assertTrue(modelo.id > 0)

    def test_formulario_valido(self):
        self.avaliador = rh_recipes.servidor.make()
        self.modelo_ppc = modelo_ppc_make()
        self.tipo = mommy.make(models.TipoEdital, nome='Edital de Alteração')
        hoje = datetime.datetime.now()
        self.inicio_inscricao = proximo_dia(hoje + relativedelta(days=1))
        self.fim_inscricao = proximo_dia(hoje + relativedelta(days=2))
        self.inicio_analise = proximo_dia(hoje + relativedelta(days=3))
        self.fim_analise = proximo_dia(hoje + relativedelta(days=4))
        self.inicio_ajuste = proximo_dia(hoje + relativedelta(days=5))
        self.fim_ajuste = proximo_dia(hoje + relativedelta(days=6))
        self.data_resultado = proximo_dia(hoje + relativedelta(days=7))

        self.data = {
            'nome': 'Alteração',
            'numero': '2',
            'ano': 2019,
            'tipo': self.tipo.id,
            'quantidade_avaliadores': 2,
            'avaliadores': [self.avaliador.id],
            'modelo_ppc': self.modelo_ppc.id,
            'inicio_inscricao': self.inicio_inscricao,
            'fim_inscricao': self.fim_inscricao,
            'inicio_analise': self.inicio_analise,
            'fim_analise': self.fim_analise,
            'inicio_ajuste': self.inicio_ajuste,
            'fim_ajuste': self.fim_ajuste,
            'data_resultado': self.data_resultado
        }
        self.files = {
            'arquivo': SimpleUploadedFile('teste.pdf', b'conteudo')
        }
        form = forms.EditalForm(data=self.data, files=self.files)
        self.assertEqual(form.is_valid(), True)


class InscricaoTesteCase(SuapTestCase):

    def setUp(self):
        super(InscricaoTesteCase, self).setUp()
        grupo = Group.objects.get(name=u'Membros da Comissão Editais de PPC')
        grupo.user_set.add(self.servidor_a.user)
        funcao_atividade = mommy.make(
            'rh.Atividade',
            codigo='0062'
        )

        models.Servidor.objects.filter(id=self.servidor_a.id).update(
            setor=self.setor_raiz_suap,
            setor_lotacao=self.setor_raiz_siape,
            setor_funcao=self.setor_raiz_siape,
            setor_exercicio=self.setor_raiz_suap,
            funcao_atividade=funcao_atividade
        )
        self.servidor_a.refresh_from_db()

    @mock.patch('documento_eletronico.models.tl.get_request')
    def test_criar_inscricao(self, mock_tl):
        mock_tl.return_value.META = {'REMOTE_ADDR': '192.168.1.5'}

        self.acessar_como(self.servidor_a)

        edital = mommy.make(
            models.Edital,
            modelo_ppc=modelo_ppc_make()
        )

        portaria = mommy.make(
            'documento_eletronico.DocumentoTexto',
            usuario_criacao=self.servidor_a.user,
            setor_dono=self.servidor_a.setor
        )
        mommy.make(
            models.Inscricao,
            edital=edital,
            portaria=portaria,
            ppc=edital.modelo_ppc,
        )

        response = self.client.get(reverse('admin:editais_ppc_inscricao_changelist'))
        self.assertContains(response, 'Inscrições')


class DocumentoFormTesteCase(TestCase):

    def setUp(self):
        super(DocumentoFormTesteCase, self).setUp()

    def test_formulario_valido(self):
        self.nome = fake.word(),
        self.url = fake.uri()

        self.data = {
            'nome': self.nome,
            'url': self.url
        }

        form = forms.DocumentoForm(data=self.data)
        self.assertEqual(form.is_valid(), True)


class SubmissaoTesteCase(SuapTestCase):

    @mock.patch('documento_eletronico.models.tl.get_request')
    @mock.patch('editais_ppc.models.GoogleCloudCredential')
    def setUp(self, mock_googlecloudcredential, mock_get_request):
        super(SubmissaoTesteCase, self).setUp()
        mock_get_request.return_value.META = {'REMOTE_ADDR': '192.168.1.5'}
        grupo = Group.objects.get(name=u'Membros da Comissão Editais de PPC')
        grupo.user_set.add(self.servidor_a.user)
        grupo = Group.objects.get(name=u'Avaliador Editais PPC')
        grupo.user_set.add(self.servidor_b.user)
        grupo = Group.objects.get(name='Gerente Sistêmico de Editais de PPC')
        grupo.user_set.add(self.servidor_c.user)

        self.hoje = datetime.datetime.now()

        self.usuario = mommy.make(
            'rh.Servidor'
        )
        funcao_atividade = mommy.make(
            'rh.Atividade',
            codigo='0062'
        )
        models.Servidor.objects.filter(id=self.servidor_a.id).update(
            setor=self.setor_raiz_suap,
            setor_lotacao=self.setor_raiz_siape,
            setor_funcao=self.setor_raiz_siape,
            setor_exercicio=self.setor_raiz_suap,
            funcao_atividade=funcao_atividade
        )
        self.servidor_a.refresh_from_db()

        edital = mommy.make(
            models.Edital,
            modelo_ppc=modelo_ppc_make()
        )
        portaria = mommy.make(
            'documento_eletronico.DocumentoTexto',
            usuario_criacao=self.servidor_a.user,
            setor_dono=self.servidor_a.setor
        )
        self.inscricao = mommy.make(
            models.Inscricao,
            edital=edital,
            portaria=portaria,
            ppc=edital.modelo_ppc,
            membros=[self.servidor_a]
        )

        self.submissao = mommy.make(
            models.Submissao,
            usuario=self.servidor_a,
            inscricao=self.inscricao,
            avaliadores=[self.servidor_b]
        )

        self.situacao = mommy.make(
            models.SituacaoPPC,
            nome='Deferido',
            impeditiva=False,
            ativa=True
        )

    def test_criar_submissao(self):

        self.acessar_como(self.servidor_a)

        response = self.client.get(reverse('admin:editais_ppc_submissao_changelist'))
        self.assertContains(
            response,
            '<a href="{}">Editar Avaliadores</a>'.format(
                reverse('admin:editais_ppc_submissao_change', args=[self.submissao.id])
            )
        )

    def test_criar_avaliacao_deferida(self):

        self.acessar_como(self.servidor_b)

        self.avaliacao_data = {
            'avaliador': self.servidor_b.id,
            'submissao': self.submissao.id,
            'situacao': self.situacao.id,
            'justificativa': 'ppc avaliado com sucesso',
            'solicitacoes-TOTAL_FORMS': 1,
            'solicitacoes-INITIAL_FORMS': 0,
            'solicitacoes-MIN_NUM_FORMS': 0,
            'solicitacoes-MAX_NUM_FORMS': 1000
        }

        self.assertEqual(models.Avaliacao.objects.count(), 0)
        self.client.post(
            reverse('admin:editais_ppc_avaliacao_add') + '?submissao={}'.format(self.submissao.id),
            self.avaliacao_data,
            follow=True
        )
        avaliacao = models.Avaliacao.objects.last()
        url = reverse('admin:editais_ppc_avaliacao_changelist')
        response = self.client.get(url)
        url = reverse('admin:editais_ppc_avaliacao_view', args=[avaliacao.pk])
        self.assertContains(
            response,
            url
        )

    def test_definir_resultado_deferido(self):

        self.acessar_como(self.servidor_c)
        self.resultado = {
            'situacao': self.situacao.id,
            'submissao': self.submissao.id
        }
        self.assertEqual(models.Resultado.objects.count(), 0)
        self.client.post(
            reverse('admin:editais_ppc_resultado_add'),
            self.resultado,
            follow=True
        )
        resultado = models.Resultado.objects.last()
        url = reverse('admin:editais_ppc_resultado_changelist')
        response = self.client.get(url)
        url = reverse('admin:editais_ppc_resultado_change', args=[resultado.pk])
        self.assertContains(
            response,
            url
        )
