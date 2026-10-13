from decimal import Decimal

from django.test import SimpleTestCase

from catalog.commission import split_commission
from catalog.models import DoctorClinic


class CommissionSplitTests(SimpleTestCase):
    def test_percentage_split(self):
        result = split_commission(
            Decimal("2000.00"),
            DoctorClinic.CommissionType.PERCENTAGE,
            Decimal("20.00"),
        )
        self.assertEqual(result["clinic_share"], Decimal("400.00"))
        self.assertEqual(result["doctor_share"], Decimal("1600.00"))

    def test_fixed_capped_at_fee(self):
        result = split_commission(
            Decimal("2000.00"),
            DoctorClinic.CommissionType.FIXED,
            Decimal("5000.00"),
        )
        self.assertEqual(result["clinic_share"], Decimal("2000.00"))
        self.assertEqual(result["doctor_share"], Decimal("0.00"))

    def test_zero_fee(self):
        result = split_commission(
            Decimal("0"),
            DoctorClinic.CommissionType.PERCENTAGE,
            Decimal("20"),
        )
        self.assertEqual(result["clinic_share"], Decimal("0.00"))
        self.assertEqual(result["doctor_share"], Decimal("0.00"))
