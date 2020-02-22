from django.contrib import admin
from example_app import models, tasks











class ModelAdminPlus(object):
    def save_model(self, request, obj, form, change):
        pass


@admin.register(models.ModeloPPC)
class ModeloPPCAdmin(ModelAdminPlus):
    list_display = ('nome', 'url', 'google_id')
    search_fields = ('nome',)
    list_filter = ('nome', 'google_id')
    fields = ['nome']
    list_display_icons = True

    def save_model(self, request, obj, form, change):
        super(ModeloPPCAdmin, self).save_model(request, obj, form, change)
        if not change:
            tasks.criar_documento.delay(obj.id)

