# Django com Graphql

Projeto desenvolvido usando a linguagem Python com Django e seu módulo do graphql. Tem por objetivo explicar o funcionamento do graphql.  

## Pré-requisitos

### Pip

Comando para instalação do PIP:

```sh
sudo apt-get install python3-pip
```

### VirtualEnv

Recomenda-se configurar o ambiente dentro de uma VirtualEnv. Como alternativa temos o [VirtualEnvWrapper](https://virtualenvwrapper.readthedocs.io/en/latest/index.html), segue abaixo um tutorial para instalação. Para mais informações, consulte o guia de instalação neste [link](https://virtualenvwrapper.readthedocs.io/en/latest/install.html).

```sh
pip install virtualenvwrapper
```

ou

```sh
sudo pip install virtualenvwrapper
```

Após isso, vá na pasta do seu usuário(~/ ou home/"nome do seu usuario") e cole estes comandos:

```sh
echo 'export WORKON_HOME=$HOME/.virtualenvs' >> .bashrc
echo 'source ~/.local/bin/virtualenvwrapper.sh' >> .bashrc
```
Caso queira configurar o python usado, execute este comando:

```sh
echo 'export VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3' >> .bashrc
```

#### Comandos básicos do VirtualEnvWrapper

Criar uma virtualenv:

```sh
mkvirtualenv "nome"
```

Caso não tenha configurado o Python da Virtualenvwrapper, quando criar a virtualenv adicione a flag --python:

```sh
mkvirtualenv "nome" --python="caminho do python instalado"
```

Ativar uma virtualenv:

```sh
workon "nome"
```
## Instalando e configurando o Django e o Graphene

```
$ pip install Django
$ pip install graphene_django
``` 
## Criando um projeto Django

```
$ django-admin.py startproject django_graphql_movies 
```
## Entre na pasta do projeto e crie a aplicação movies
```
$ cd django_graphql_movies/
$ django-admin.py startapp movies
```

## Criando os modelos de ator e filme
Insira o código abaixo no arquivo models.py da app movies:
```
from django.db import models

class Actor(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ('name',)

class Movie(models.Model):
    title = models.CharField(max_length=100)
    actors = models.ManyToManyField(Actor)
    year = models.IntegerField()

    def __str__(self):
        return self.title

    class Meta:
        ordering = ('title',)
``` 
## Registre a aplicação movies dentro do INSTALLED_APPS no arquivo settings.py do projeto:

```
INSTALLED_APPS = [
    'graphene_django',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'movies',
]

```
## Crie os arquivos de migação e os execute, com os seguintes comandos:
```
$ python manage.py makemigrations
$ python manage.py migrate       

```

## Povoando o banco de dados para testar com o graphql:
Crie o arquivo movies.json na raiz do projeto e insira o seguinte código:

```
[
  {
    "model": "movies.actor",
    "pk": 1,
    "fields": {
      "name": "Michael B. Jordan"
    }
  },
  {
    "model": "movies.actor",
    "pk": 2,
    "fields": {
      "name": "Sylvester Stallone"
    }
  },
  {
    "model": "movies.movie",
    "pk": 1,
    "fields": {
      "title": "Creed",
      "actors": [1, 2],
      "year": "2015"
    }
  }
]
```
Após isso, execute o comando para inserir esses dados no banco:

```
$ python manage.py loaddata movies.json
```

O terminal deve exibir a seguinte saída: 

```
Installed 3 object(s) from 1 fixture(s)
```
## Criando o Schema com o Graphene

## Queries: 
Dentro da app movies,crie o arquivo schema.py

Insira o seguinte código para criar os nossos tipos:

```
import graphene
from graphene_django.types import DjangoObjectType, ObjectType
from django_graphql_movies.movies.models import Actor, Movie

# Cria um type do GraphQL para o modelo Actor
class ActorType(DjangoObjectType):
    class Meta:
        model = Actor

# Cria um type do GraphQL para o modelo Movie
class MovieType(DjangoObjectType):
    class Meta:
        model = Movie
```

No mesmo arquivo, insira o seguinte código para criar o type Query:

```

# Create a Query type
class Query(ObjectType):
    actor = graphene.Field(ActorType, id=graphene.Int())
    movie = graphene.Field(MovieType, id=graphene.Int())
    actors = graphene.List(ActorType)
    movies= graphene.List(MovieType)

    def resolve_actor(self, info, **kwargs):
        id = kwargs.get('id')

        if id is not None:
            return Actor.objects.get(pk=id)

        return None

    def resolve_movie(self, info, **kwargs):
        id = kwargs.get('id')

        if id is not None:
            return Movie.objects.get(pk=id)

        return None

    def resolve_actors(self, info, **kwargs):
        return Actor.objects.all()

    def resolve_movies(self, info, **kwargs):
        return Movie.objects.all()
```

##Criando Mutations

Primeiro, vamos criar dois inputs referentes aos nosso modelos.Insira o código abaixo:

```
# Create Input Object Types
class ActorInput(graphene.InputObjectType):
    id = graphene.ID()
    name = graphene.String()

class MovieInput(graphene.InputObjectType):
    id = graphene.ID()
    title = graphene.String()
    actors = graphene.List(ActorInput)
    year = graphene.Int()
```

Adicione a mutation para os atores:
```
# Create mutations for actors
class CreateActor(graphene.Mutation):
    class Arguments:
        input = ActorInput(required=True)

    ok = graphene.Boolean()
    actor = graphene.Field(ActorType)

    @staticmethod
    def mutate(root, info, input=None):
        ok = True
        actor_instance = Actor(name=input.name)
        actor_instance.save()
        return CreateActor(ok=ok, actor=actor_instance)

class UpdateActor(graphene.Mutation):
    class Arguments:
        id = graphene.Int(required=True)
        input = ActorInput(required=True)

    ok = graphene.Boolean()
    actor = graphene.Field(ActorType)

    @staticmethod
    def mutate(root, info, id, input=None):
        ok = False
        actor_instance = Actor.objects.get(pk=id)
        if actor_instance:
            ok = True
            actor_instance.name = input.name
            actor_instance.save()
            return UpdateActor(ok=ok, actor=actor_instance)
        return UpdateActor(ok=ok, actor=None)
```
Adicione a mutation para os filmes:

```
# Create mutations for movies
class CreateMovie(graphene.Mutation):
    class Arguments:
        input = MovieInput(required=True)

    ok = graphene.Boolean()
    movie = graphene.Field(MovieType)

    @staticmethod
    def mutate(root, info, input=None):
        ok = True
        actors = []
        for actor_input in input.actors:
          actor = Actor.objects.get(pk=actor_input.id)
          if actor is None:
            return CreateMovie(ok=False, movie=None)
          actors.append(actor)
        movie_instance = Movie(
          title=input.title,
          year=input.year
          )
        movie_instance.save()
        movie_instance.actors.set(actors)
        return CreateMovie(ok=ok, movie=movie_instance)


class UpdateMovie(graphene.Mutation):
    class Arguments:
        id = graphene.Int(required=True)
        input = MovieInput(required=True)

    ok = graphene.Boolean()
    movie = graphene.Field(MovieType)

    @staticmethod
    def mutate(root, info, id, input=None):
        ok = False
        movie_instance = Movie.objects.get(pk=id)
        if movie_instance:
            ok = True
            actors = []
            for actor_input in input.actors:
              actor = Actor.objects.get(pk=actor_input.id)
              if actor is None:
                return UpdateMovie(ok=False, movie=None)
              actors.append(actor)
            movie_instance.title=input.title
            movie_instance.year=input.yearce.save()
            movie_instance.actors.set(actors)
            return UpdateMovie(ok=ok, movie=movie_instance)
        return UpdateMovie(ok=ok, movie=None)
```
# Criando nosso Schema
Ao final do arquivo, adicione a seguinte linha:
 ```
schema = graphene.Schema(query=Query, mutation=Mutation)
```
# Registrando o schema a nível de projeto:

Crie um novo arquivo schema.py na raiz do projeto e adicione o código abaixo:

```
import graphene
import django_graphql_movies.movies.schema

class Query(django_graphql_movies.movies.schema.Query, graphene.ObjectType):
    # This class will inherit from multiple Queries
    # as we begin to add more apps to our project
    pass

class Mutation(django_graphql_movies.movies.schema.Mutation, graphene.ObjectType):
    # This class will inherit from multiple Queries
    # as we begin to add more apps to our project
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```
  
No settings.py do projeto, insira 'graphene_django' no final do INSTALLED_APPS

Após o INSTALLED_APPS, insira o código abaixo:

GRAPHENE = {
    'SCHEMA': 'django_graphql_movies.schema.schema'
}

##Criando rota para acessar o graphql

no arquivo django_graphql_movies/urls.py, altere o código e deixe da seguinte forma:

 ```
from django.contrib import admin
from django.urls import path
from graphene_django.views import GraphQLView
from django_graphql_movies.schema import schema

urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', GraphQLView.as_view(graphiql=True)),
]
```

## Testando nossa API 
Execute o servidor com o comando abaixo:
```
$ python manage.py runserver
```

Acesse a rota para o graphql:
```
http://127.0.0.1:8000/graphql/
```

##Executando Queries

Obtendo id e nome de todos os atores:

```
query getActors {
  actors {
    id
    name
  }
}
```

Obtendo filme de id 1 com os campos selecionados:

```
query getMovie {
  movie(id: 1) {
    id
    title
    actors {
      id
      name
    }
  }
}
```

##Executando Mutations

Criando um ator pssando o nome:

```
mutation createActor {
  createActor(input: {
    name: "Tom Hanks"
  }) {
    ok
    actor {
      id
      name
    }
  }
}
```

Criando um filme passando o título, os atores e o ano:

```
mutation updateMovie {
  updateMovie(id: 2, input: {
    title: "Cast Away",
    actors: [
      {
        id: 3
      }
    ]
    year: 2000
  }) {
    ok
    movie{
      id
      title
      actors {
        id
        name
      }
      year
    }
  }
}
```

Para uma aplicação externa se comunicar com sua API, precisamos 
alterar o arquivo django_graphql_movies/urls.py:

```
from django.contrib import admin
from django.urls import path
from graphene_django.views import GraphQLView
from django_graphql_movies.schema import schema
from django.views.decorators.csrf import csrf_exempt # New library

urlpatterns = [
    path('admin/', admin.site.urls),
    path('graphql/', csrf_exempt(GraphQLView.as_view(graphiql=True))),
]
```

Para testar, insira no seu terminal:
```
$ curl \
  -X POST \
  -H "Content-Type: application/json" \
  --data '{ "query": "{ actors { name } }" }' \
  http://127.0.0.1:8000/graphql/
```

Com isso, conseguimos criar do zero e testar nossa aplicação com o Django e GraphQL. 