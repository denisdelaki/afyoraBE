# billing/utils.py
from django.db.models import Q
from pharmacy.models import Prescription, Drug


def get_patient_pharmacy_charges(patient, facility_id=None):
    """
    Calculate itemized pharmacy charges for a patient in a facility.
    Returns: (total_amount, items_list)
    """
    fac_id = facility_id or patient.facility_id

    # Find prescriptions for this patient (match patient_id or string patient pk)
    patient_identifiers = [patient.patient_id, str(patient.id)]
    prescriptions = Prescription.objects.filter(
        facility_id=fac_id,
        patient_id__in=patient_identifiers
    ).exclude(status='Cancelled')

    items_list = []
    total_amount = 0.0

    # Build drug price lookup dictionary for facility
    drugs_by_id = {}
    drugs_by_name = {}
    if fac_id:
        for drug in Drug.objects.filter(facility_id=fac_id):
            drugs_by_id[drug.drug_id.upper()] = float(drug.price)
            drugs_by_name[drug.name.lower()] = float(drug.price)

    for rx in prescriptions:
        rx_drugs = rx.drugs if isinstance(rx.drugs, list) else []
        for drug_item in rx_drugs:
            if not isinstance(drug_item, dict):
                continue

            drug_name = drug_item.get('name') or drug_item.get('drug_name') or 'Prescribed Drug'
            drug_id_val = str(drug_item.get('id', '')).upper()
            qty = int(drug_item.get('quantity') or drug_item.get('qty') or 1)

            unit_price = 0.0
            if 'price' in drug_item and drug_item['price'] is not None:
                unit_price = float(drug_item['price'])
            elif 'amount' in drug_item and drug_item['amount'] is not None:
                unit_price = float(drug_item['amount'])
            elif drug_id_val in drugs_by_id:
                unit_price = drugs_by_id[drug_id_val]
            elif drug_name.lower() in drugs_by_name:
                unit_price = drugs_by_name[drug_name.lower()]

            item_total = round(qty * unit_price, 2)
            total_amount += item_total

            service_name = f"Pharmacy: {drug_name} (x{qty})"
            items_list.append({
                'service': service_name,
                'amount': item_total,
                'drug_name': drug_name,
                'quantity': qty,
                'unit_price': unit_price,
                'prescription_id': rx.prescription_id,
                'date': str(rx.date)
            })

    return round(total_amount, 2), items_list


def get_patient_lab_charges(patient, facility_id=None):
    """
    Calculate itemized laboratory test charges for a patient in a facility.
    Fetches all LabRequests (not Cancelled) and retrieves the test price from
    the related LabTest catalogue entry.
    Returns: (total_amount, items_list)
    """
    from laboratory.models import LabRequest

    fac_id = facility_id or patient.facility_id
    patient_identifiers = [patient.patient_id, str(patient.id)]

    requests = LabRequest.objects.select_related('test').filter(
        facility_id=fac_id,
        patient_id__in=patient_identifiers
    ).exclude(status='Cancelled').order_by('-order_date')

    items_list = []
    total_amount = 0.0

    for req in requests:
        test_name = req.test.name if req.test else 'Lab Test'
        unit_price = float(req.test.price) if req.test and req.test.price else 0.0

        items_list.append({
            'service': f"Lab: {test_name}",
            'amount': unit_price,
            'test_name': test_name,
            'unit_price': unit_price,
            'request_id': req.request_id,
            'status': req.status,
            'date': str(req.order_date)
        })
        total_amount += unit_price

    return round(total_amount, 2), items_list


def get_patient_radiology_charges(patient, facility_id=None):
    """
    Calculate itemized radiology/imaging charges for a patient in a facility.
    Pulls all non-pending ImagingRequests, looks up the associated ImagingStudy price.
    Returns: (total_amount, items_list)
    """
    from radiology.models import ImagingRequest

    fac_id = facility_id or patient.facility_id
    patient_identifiers = [patient.patient_id, str(patient.id)]

    requests = ImagingRequest.objects.select_related('study').filter(
        facility_id=fac_id,
        patient_id__in=patient_identifiers
    ).exclude(status='Cancelled').order_by('-order_date')

    items_list = []
    total_amount = 0.0

    for req in requests:
        study_name = req.study.name if req.study else 'Imaging Study'
        unit_price = float(req.study.price) if req.study and req.study.price else 0.0

        items_list.append({
            'service': f"Radiology: {study_name}",
            'amount': unit_price,
            'study_name': study_name,
            'unit_price': unit_price,
            'request_id': req.request_id,
            'status': req.status,
            'date': str(req.order_date)
        })
        total_amount += unit_price

    return round(total_amount, 2), items_list
