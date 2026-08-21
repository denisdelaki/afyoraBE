from rest_framework import serializers
from .models import SavedReport


class SavedReportSerializer(serializers.ModelSerializer):
    reportType = serializers.CharField(source='report_type', required=False)
    timeRange = serializers.CharField(source='time_range', required=False)
    chartType = serializers.CharField(source='chart_type', required=False)
    allowedRoles = serializers.JSONField(source='allowed_roles', required=False)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    createdBy = serializers.CharField(
        source='created_by', required=False, allow_blank=True
    )
    facilityId = serializers.IntegerField(
        source='facility_id', required=False, allow_null=True
    )

    class Meta:
        model = SavedReport
        fields = [
            'id',
            'facilityId',
            'title',
            'description',
            'reportType',
            'timeRange',
            'department',
            'chartType',
            'allowedRoles',
            'createdBy',
            'createdAt',
            'updatedAt',
        ]

    def to_internal_value(self, data):
        mutable_data = data.copy()
        if 'reportType' in mutable_data:
            mutable_data['report_type'] = mutable_data.pop('reportType')
        if 'timeRange' in mutable_data:
            mutable_data['time_range'] = mutable_data.pop('timeRange')
        if 'chartType' in mutable_data:
            mutable_data['chart_type'] = mutable_data.pop('chartType')
        if 'allowedRoles' in mutable_data:
            mutable_data['allowed_roles'] = mutable_data.pop('allowedRoles')
        if 'createdBy' in mutable_data:
            mutable_data['created_by'] = mutable_data.pop('createdBy')
        if 'facilityId' in mutable_data:
            mutable_data['facility'] = mutable_data.pop('facilityId')
        return super().to_internal_value(mutable_data)
