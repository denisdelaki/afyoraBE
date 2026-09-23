from rest_framework import serializers
from .models import KNHTSConcept, MedicationHPT, TerminologyCatalog


class KNHTSConceptSerializer(serializers.ModelSerializer):
    class Meta:
        model = KNHTSConcept
        fields = '__all__'


class MedicationHPTSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicationHPT
        fields = '__all__'


class TerminologyCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminologyCatalog
        fields = '__all__'
