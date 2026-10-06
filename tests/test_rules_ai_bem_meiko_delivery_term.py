import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import App.Rules_AI_BEM_MEIKO as rules


def _delivery_block(document_type, file_name, delivery_term=None):
    fields = [
        f"Loai chung tu: {document_type}",
        f"File Name: {file_name}",
    ]
    if delivery_term is not None:
        fields.append(f"Dieu kien giao hang: {delivery_term}")
    return "{ " + " | ".join(fields) + " }"


class FixedCompareDocumentBlockTests(unittest.TestCase):
    def test_parser_handles_interleaved_blocks_and_reordered_fields(self):
        content = """
header text
{ Delivery Term: FOB HAI-PHONG | File Name: PO_1.pdf | Loai chung tu: PO }
unrelated text
{ File Name: INV_1.pdf | Loai chung tu: COMMERCIAL INVOICE | Delivery Term: CIF TOKYO-TO }
{ Dieu kien giao hang: CIP NOI BAI | Loai chung tu: CUSTOMSHEET | File Name: CUS_1.xlsx }
footer text
"""

        self.assertEqual(
            rules._parse_fixed_compare_document_blocks(content),
            [
                {"DELIVERYTERM": "FOB HAI-PHONG", "FILENAME": "PO_1.pdf", "LOAICHUNGTU": "PO"},
                {"FILENAME": "INV_1.pdf", "LOAICHUNGTU": "COMMERCIALINVOICE", "DELIVERYTERM": "CIF TOKYO-TO"},
                {"DIEUKIENGIAOHANG": "CIP NOI BAI", "LOAICHUNGTU": "CUSTOMSHEET", "FILENAME": "CUS_1.xlsx"},
            ],
        )

    def test_accented_delivery_field_name_builds_matching_result(self):
        content = "\n".join((
            "{ Loai chung tu: PO | File Name: po.pdf | Điều kiện giao hàng: CIF TOKYO }",
            "{ Loai chung tu: CUSTOMSHEET | File Name: custom.xlsx | Điều kiện giao hàng: CIF TOKYO-TO }",
        ))

        result = rules._build_delivery_term_result(content, "Điều kiện giao hàng")

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")


class CompareRuleFormationFallbackTests(unittest.TestCase):
    def test_kethua_phieucongtac_resolves_like_kethua_congno_for_every_rule(self):
        for dntt_type, dntt_rules in rules.COMPARE_RULES.items():
            congno_rules = dntt_rules.get("KETHUA_CONGNO") or {}
            for installment, criteria in congno_rules.items():
                for criterion_name in criteria:
                    with self.subTest(
                        dntt_type=dntt_type,
                        installment=installment,
                        criterion_name=criterion_name,
                    ):
                        base_prompt = {
                            "PromptType": "DOICHIEU",
                            "DnttType": dntt_type,
                            "Installment": "" if installment == "DEFAULT" else installment,
                            "CriterionName": criterion_name,
                        }
                        congno_rule = rules._resolve_compare_rule({
                            **base_prompt,
                            "FormationID": "KETHUA_CONGNO",
                        })
                        phieucongtac_rule = rules._resolve_compare_rule({
                            **base_prompt,
                            "FormationID": "KETHUA_PHIEUCONGTAC",
                        })

                        self.assertEqual(phieucongtac_rule, congno_rule)


class DeliveryTermNormalizationTests(unittest.TestCase):
    def assertDeliveryTerm(self, value, *, incoterm, country="", province="", location=""):
        self.assertEqual(
            rules._normalize_delivery_term(value),
            {"incoterm": incoterm, "country": country, "province": province, "location": location},
        )

    def test_bare_incoterm_is_normalized(self):
        self.assertDeliveryTerm("cif", incoterm="CIF")

    def test_ex_factory_variants_normalize_to_bare_exw(self):
        for value in ("EX-FACTORY", "EX FACTORY", "EXW FACTORY", "EXWORK", "Ex-work"):
            with self.subTest(value=value):
                self.assertDeliveryTerm(value, incoterm="EXW")

    def test_full_incoterm_name_variants_normalize_to_codes(self):
        cases = {
            "Free Carrier Warehouse": "FCA",
            "Free Alongside Ship Warehouse": "FAS",
            "Free-On-Board Warehouse": "FOB",
            "Cost and Freight Warehouse": "CFR",
            "Cost Insurance Freight Warehouse": "CIF",
            "Carriage Paid To Warehouse": "CPT",
            "Carriage and Insurance Paid To Warehouse": "CIP",
            "Delivered At Place Warehouse": "DAP",
            "Delivered At Place Unloaded Warehouse": "DPU",
            "Delivered At Terminal Warehouse": "DAT",
            "Delivered Duty Paid Warehouse": "DDP",
            "Delivered Duty Unpaid Warehouse": "DDU",
        }

        for value, incoterm in cases.items():
            with self.subTest(value=value):
                self.assertDeliveryTerm(value, incoterm=incoterm, location="WAREHOUSE")

    def test_compact_full_incoterm_name_variants_normalize_to_codes(self):
        cases = {
            "FreeCarrier Warehouse": "FCA",
            "FreeAlongsideShip Warehouse": "FAS",
            "FreeOnBoard Warehouse": "FOB",
            "CostAndFreight Warehouse": "CFR",
            "CostInsuranceFreight Warehouse": "CIF",
            "CarriagePaidTo Warehouse": "CPT",
            "CarriageAndInsurancePaidTo Warehouse": "CIP",
            "DeliveredAtPlace Warehouse": "DAP",
            "DeliveredAtPlaceUnloaded Warehouse": "DPU",
            "DeliveredAtTerminal Warehouse": "DAT",
            "DeliveredDutyPaid Warehouse": "DDP",
            "DeliveredDutyUnpaid Warehouse": "DDU",
        }

        for value, incoterm in cases.items():
            with self.subTest(value=value):
                self.assertDeliveryTerm(value, incoterm=incoterm, location="WAREHOUSE")

    def test_every_incoterm_alias_resolves_to_canonical_code(self):
        for incoterm, aliases in rules.DELIVERY_TERM_INCOTERM_ALIASES.items():
            for alias in aliases:
                with self.subTest(incoterm=incoterm, alias=alias):
                    self.assertDeliveryTerm(alias, incoterm=incoterm)

    def test_country_aliases_are_normalized(self):
        country_aliases = {
            "VIETNAM": ("VIETNAM", "VIET NAM", "VN", "VIE", "VI\u1ec6T NAM"),
            "JAPAN": ("JAPAN", "JP", "JPN", "NHAT BAN", "NH\u1eacT B\u1ea2N"),
            "CHINA": ("CHINA", "CN", "CHN", "TRUNG QUOC", "TRUNG QU\u1ed0C"),
            "TAIWAN": ("TAIWAN", "TAI WAN", "TW", "TWN", "DAI LOAN", "\u0110\u00c0I LOAN"),
            "SINGAPORE": ("SINGAPORE", "SG", "SGP", "SINGAPURA"),
        }

        for country, aliases in country_aliases.items():
            for alias in aliases:
                with self.subTest(country=country, alias=alias):
                    self.assertDeliveryTerm("CIF " + alias, incoterm="CIF", country=country)

    def test_every_country_catalog_alias_resolves_to_canonical_country(self):
        for country, info in rules.DELIVERY_TERM_COUNTRY_CATALOG.items():
            for alias in info["aliases"]:
                with self.subTest(country=country, alias=alias):
                    self.assertDeliveryTerm(
                        f"CIF {alias}",
                        incoterm="CIF",
                        country=country,
                    )

    def test_country_catalog_contains_all_supported_countries(self):
        self.assertEqual(
            set(rules.DELIVERY_TERM_COUNTRY_CATALOG),
            {"VIETNAM", "JAPAN", "CHINA", "TAIWAN", "SINGAPORE"},
        )

    def test_province_catalog_is_complete_for_supported_countries(self):
        expected_counts = {
            "VIETNAM": 34,
            "JAPAN": 47,
            "CHINA": 33,
            "TAIWAN": 22,
        }
        actual_counts = {
            country: sum(
                1
                for info in rules.DELIVERY_TERM_PROVINCE_CATALOG.values()
                if info["country"] == country
            )
            for country in expected_counts
        }

        self.assertEqual(actual_counts, expected_counts)

    def test_common_country_and_province_alias_variants_are_recognized(self):
        cases = {
            "CIF HaNoi": ("VIETNAM", "HA_NOI"),
            "CIF TP.HCM": ("VIETNAM", "HO_CHI_MINH_CITY"),
            "CIF SAIGON": ("VIETNAM", "HO_CHI_MINH_CITY"),
            "CIF HOKKAIDO PREFECTURE": ("JAPAN", "HOKKAIDO"),
            "CIF GUANGXI ZHUANG": ("CHINA", "GUANGXI"),
            "CIF NEWTAIPEI": ("TAIWAN", "NEW_TAIPEI"),
            "CIF \u9ad8\u96c4\u5e02": ("TAIWAN", "KAOHSIUNG"),
        }

        for value, (country, province) in cases.items():
            with self.subTest(value=value):
                self.assertDeliveryTerm(
                    value,
                    incoterm="CIF",
                    country=country,
                    province=province,
                )

    def test_province_aliases_infer_parent_country(self):
        cases = {
            "HAI-PHONG": ("VIETNAM", "HAI_PHONG"),
            "TOKYO-TO": ("JAPAN", "TOKYO"),
            "GUANGZHOU": ("CHINA", "GUANGDONG"),
            "\u6771\u4eac\u90fd": ("JAPAN", "TOKYO"),
            "B\u1eaeC NINH": ("VIETNAM", "BAC_NINH"),
            "\u5e7f\u4e1c\u7701": ("CHINA", "GUANGDONG"),
            "HOABINH": ("VIETNAM", "PHU_THO"),
            "HANOI": ("VIETNAM", "HA_NOI"),
        }

        for alias, (country, province) in cases.items():
            with self.subTest(alias=alias):
                self.assertDeliveryTerm("FOB " + alias, incoterm="FOB", country=country, province=province)

    def test_country_and_province_combination_is_recognized_in_both_orders(self):
        for location in (
            "VIETNAM HAIPHONG",
            "HAIPHONG VIETNAM",
            "VIET NAM HAI PHONG",
            "HAI PHONG VIET NAM",
        ):
            with self.subTest(location=location):
                self.assertDeliveryTerm(
                    "CIF " + location,
                    incoterm="CIF",
                    country="VIETNAM",
                    province="HAI_PHONG",
                )

    def test_every_province_catalog_alias_resolves_to_parent_and_canonical_province(self):
        for province, info in rules.DELIVERY_TERM_PROVINCE_CATALOG.items():
            for alias in info["aliases"]:
                with self.subTest(province=province, alias=alias):
                    self.assertDeliveryTerm(
                        f"FOB {alias}",
                        incoterm="FOB",
                        country=info["country"],
                        province=province,
                    )

    def test_location_separators_and_whitespace_are_normalized(self):
        values = (
            "CIF...HAI__PHONG",
            "CIF   HAI   PHONG",
            "CIF._-HAI__..PHONG",
            "CIF\t HAI  \n PHONG",
        )
        for value in values:
            with self.subTest(value=value):
                self.assertDeliveryTerm(
                    value,
                    incoterm="CIF",
                    country="VIETNAM",
                    province="HAI_PHONG",
                )

    def test_trailing_incoterms_version_is_ignored(self):
        for value in (
            "CIF NOI BAI, INCOTERMS 2020",
            "CIF NOI BAI INCOTERM 2020",
        ):
            with self.subTest(value=value):
                self.assertDeliveryTerm(
                    value,
                    incoterm="CIF",
                    location="NOI BAI",
                )

    def test_trailing_text_after_catalog_location_is_ignored(self):
        for value in (
            "CIF NOI BAI BY AIR",
            "CIF NOI BAI ABC.. XYZ..",
            "CIF NOIBAI OTHER TEXT",
        ):
            with self.subTest(value=value):
                self.assertDeliveryTerm(
                    value,
                    incoterm="CIF",
                    location="NOI BAI",
                )

    def test_trailing_text_after_province_alias_is_ignored(self):
        self.assertDeliveryTerm(
            "CIF HOABINH ABCXYZ",
            incoterm="CIF",
            country="VIETNAM",
            province="PHU_THO",
        )

    def test_loyang_distribution_center_infers_singapore(self):
        self.assertDeliveryTerm(
            "FCA LOYANG DC",
            incoterm="FCA",
            country="SINGAPORE",
            location="LOYANG",
        )

    def test_common_singapore_logistics_areas_are_normalized(self):
        cases = {
            "FCA JURONG ISLAND": "JURONG",
            "FCA TUAS PORT": "TUAS",
            "FCA CHANGI BUSINESS PARK": "CHANGI",
            "FCA WOODLANDS INDUSTRIAL PARK": "WOODLANDS",
            "FCA TAMPINES REGIONAL CENTRE": "TAMPINES",
            "FCA PIONEER SECTOR": "PIONEER",
            "FCA BOON LAY": "BOON LAY",
            "FCA SELETAR AEROSPACE PARK": "SELETAR",
            "FCA SUNGEI KADUT INDUSTRIAL ESTATE": "SUNGEI KADUT",
            "FCA PAYA LEBAR CENTRAL": "PAYA LEBAR",
        }

        for value, location in cases.items():
            with self.subTest(value=value):
                self.assertDeliveryTerm(
                    value,
                    incoterm="FCA",
                    country="SINGAPORE",
                    location=location,
                )

    def test_every_inferred_location_alias_resolves_to_parent_country(self):
        for info in rules.DELIVERY_TERM_LOCATION_CATALOG.values():
            if not info.get("infer_country"):
                continue
            for alias in info.get("aliases") or ():
                with self.subTest(display=info.get("display"), alias=alias):
                    self.assertDeliveryTerm(
                        f"FCA {alias}",
                        incoterm="FCA",
                        country=info["country"],
                        location=info["display"],
                    )

    def test_japanese_kana_diacritics_are_preserved_in_unknown_location(self):
        self.assertDeliveryTerm(
            "CIF \u30ca\u30b4\u30e4",
            incoterm="CIF",
            location="\u30ca\u30b4\u30e4",
        )

    def test_kana_dakuten_remains_distinct(self):
        voiced = rules._normalize_delivery_term("CIF \u30ac")
        unvoiced = rules._normalize_delivery_term("CIF \u30ab")

        self.assertEqual(voiced["location"], "\u30ac")
        self.assertEqual(unvoiced["location"], "\u30ab")
        self.assertNotEqual(voiced["location"], unvoiced["location"])

    def test_vietnamese_accents_continue_to_fold_for_lookup(self):
        self.assertDeliveryTerm(
            "CIF VI\u1ec6T NAM",
            incoterm="CIF",
            country="VIETNAM",
        )

    def test_unknown_location_is_preserved_without_geographic_inference(self):
        self.assertDeliveryTerm("CIP NOI BAI", incoterm="CIP", location="NOI BAI")

    def test_unknown_location_comparison_key_ignores_spacing_but_display_keeps_it(self):
        term = rules._normalize_delivery_term("CIF NOI BAI")

        self.assertEqual(rules._delivery_term_key(term), ("CIF", "", "", "NOIBAI"))
        self.assertEqual(rules._format_delivery_term(term), "CIF NOI BAI")

    def test_payment_noise_is_rejected(self):
        noise_values = (
            "T/T", "T/ T", "T/T BASE", "TT BASE", "BY TT", "PAYMENT",
            "PAYMENT TERM", "L/C", "LC", "NET 30", "NET 60",
        )
        for value in noise_values:
            with self.subTest(value=value):
                self.assertIsNone(rules._normalize_delivery_term(value))

    def test_value_must_begin_with_valid_incoterm(self):
        for value in ("DELIVERY CIF TOKYO", "TERM FOB HAI PHONG", "XFOB TOKYO", "FACTORY EXW"):
            with self.subTest(value=value):
                self.assertIsNone(rules._normalize_delivery_term(value))


class DeliveryTermResultTests(unittest.TestCase):
    def build_result(self, *blocks, criterion_name="Delivery criterion"):
        return rules._build_delivery_term_result("\nnoise\n".join(blocks), criterion_name)

    def assertCriteria(self, result, *, name="Delivery criterion", status, file_name, description):
        self.assertEqual(
            result,
            {
                "criteria": {
                    "CriteriaName": name,
                    "CriteriaStatus": status,
                    "FileName": file_name,
                    "Description": description,
                }
            },
        )

    def test_helper_key_format_and_mismatch_api(self):
        tokyo = rules._normalize_delivery_term("CIF TOKYO-TO")
        japan = rules._normalize_delivery_term("CIF JAPAN")
        osaka = rules._normalize_delivery_term("CIF OSAKA-FU")

        self.assertEqual(rules._delivery_term_key(tokyo), ("CIF", "JAPAN", "TOKYO", ""))
        self.assertEqual(rules._format_delivery_term(tokyo), "CIF TOKYO")
        self.assertEqual(rules._format_delivery_term(japan), "CIF JAPAN")
        self.assertEqual(rules._delivery_term_mismatch(japan, tokyo), "")
        self.assertEqual(rules._delivery_term_mismatch(tokyo, osaka), "")

    def test_bare_incoterm_covers_one_detailed_value(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF"),
            _delivery_block("COMMERCIAL INVOICE", "cinv.pdf", "CIF TOKYO"),
        )

        self.assertCriteria(
            result,
            status="OK",
            file_name="",
            description="Điều kiện giao hàng đã hoàn toàn khớp với nhau.",
        )

    def test_bare_incoterm_does_not_hide_conflicting_detailed_values(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF HAIPHONG"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF"),
            _delivery_block("COMMERCIAL INVOICE", "cinv.pdf", "CIF NOIBAI"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "po.pdf, cinv.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

    def test_tokyo_osaka_business_group_is_compatible(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF TOKYO"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF OSAKA"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_different_incoterms_return_ng_even_when_one_value_is_majority(self):
        result = self.build_result(
            _delivery_block("INVOICE", "cif-hp-1.pdf", "CIF HaiPhong"),
            _delivery_block("INVOICE", "cif-hp-2.pdf", "CIF HaiPhong"),
            _delivery_block("INVOICE", "cip-noibai.pdf", "CIP NOIBAI"),
            _delivery_block("INVOICE", "cip.pdf", "CIP"),
            _delivery_block("INVOICE", "cif.pdf", "CIF"),
            _delivery_block("PO", "po.pdf", "CIF HaiPhong"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "cif-hp-1.pdf, cip-noibai.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIP NOI BAI", criteria["Description"])

    def test_bare_different_incoterms_return_ng(self):
        result = self.build_result(
            _delivery_block("PO", "cif.pdf", "CIF"),
            _delivery_block("INVOICE", "cip.pdf", "CIP"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "cif.pdf, cip.pdf")
        self.assertIn("CIF", criteria["Description"])
        self.assertIn("CIP", criteria["Description"])

    def test_conflicting_minorities_across_document_types_return_ng(self):
        result = self.build_result(
            _delivery_block("PO", "po-cif-1.pdf", "CIF"),
            _delivery_block("PO", "po-cif-2.pdf", "CIF"),
            _delivery_block("PO", "po-haiphong.pdf", "CIF HAIPHONG"),
            _delivery_block("INVOICE", "invoice-cif-1.pdf", "CIF"),
            _delivery_block("INVOICE", "invoice-cif-2.pdf", "CIF"),
            _delivery_block("INVOICE", "invoice-noibai.pdf", "CIF NOIBAI"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "po-haiphong.pdf, invoice-noibai.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

    def test_country_and_province_in_same_country_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF JAPAN"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF TOKYO"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_country_province_combination_matches_plain_province(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF HAI PHONG"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF VIETNAM HAIPHONG"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_conflicting_country_province_combination_remains_ng(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF HAI PHONG"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF JAPAN HAIPHONG"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_different_countries_do_not_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF JAPAN"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF VIETNAM"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
        self.assertEqual(result["criteria"]["FileName"], "po.pdf, invoice.pdf")

    def test_same_unknown_locations_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF NARITA AIRPORT"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF NARITA AIRPORT"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_singapore_country_matches_loyang_location(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice.pdf", "FCA LOYANG DC"),
            _delivery_block("PO", "po.pdf", "FCA SINGAPORE"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_loyang_does_not_match_different_unknown_location(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice.pdf", "FCA LOYANG"),
            _delivery_block("PO", "po.pdf", "FCA JURONG"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_two_different_singapore_areas_do_not_match(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice.pdf", "FCA JURONG"),
            _delivery_block("PO", "po.pdf", "FCA TUAS"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_singapore_country_matches_other_catalog_area(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice.pdf", "FCA CHANGI BUSINESS PARK"),
            _delivery_block("PO", "po.pdf", "FCA SINGAPORE"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_noi_bai_matches_parent_hanoi_province(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIP NOI BAI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIP HA NOI"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_known_location_with_parenthesized_qualifier_matches_plain_alias(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIP NOI BAI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIP NOIBAI(HANOI)"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_unknown_location_spacing_does_not_cause_mismatch(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF NOI BAI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF NOIBAI"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_unknown_locations_with_more_than_80_percent_similarity_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF NOIBAI"),
            _delivery_block("INVOICE", "invoice-l.pdf", "CIF NOIBAL"),
            _delivery_block("INVOICE", "invoice-i.pdf", "CIF NOIBAI"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        self.assertNotIn(
            "có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau",
            result["criteria"]["Description"],
        )

    def test_unknown_locations_with_exactly_80_percent_similarity_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF ABCDE"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF ABCDF"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_short_delivery_location_matches_expanded_company_name(self):
        result = self.build_result(
            _delivery_block("COMMERCIALINVOICE", "commercial-invoice.pdf", "DDP MEIKO ELECTRONICS VIET NAM"),
            _delivery_block("PO", "po.pdf", "DDP MEIKO"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_meiko_abbreviation_matches_company_location(self):
        result = self.build_result(
            _delivery_block("COMMERCIALINVOICE", "commercial-invoice.pdf", "DAP MK"),
            _delivery_block("PO", "po.pdf", "DAP MEIKO"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_shared_company_prefix_does_not_merge_two_different_expanded_names(self):
        result = self.build_result(
            _delivery_block("COMMERCIALINVOICE", "commercial-invoice.pdf", "DDP MEIKO ELECTRONICS"),
            _delivery_block("PO", "po.pdf", "DDP MEIKO INDUSTRIES"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_different_trailing_text_after_noi_bai_is_ignored(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice.pdf", "CIF NOI BAI BY AIR"),
            _delivery_block("PO", "po.pdf", "CIF NOI BAI ABC XYZ"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_different_trailing_text_after_hoa_binh_is_ignored(self):
        result = self.build_result(
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF HOABINH ABCXYZ"),
            _delivery_block("COMMERCIALINVOICE", "commercial-invoice.pdf", "CIF HOA BINH OTHER TEXT"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_country_name_with_ocr_typo_matches_known_country(self):
        for correct_value, ocr_value in (
            ("CIF VIETNAM", "CIF VIETNAN"),
            ("CIF JAPAN", "CIF IAPAN"),
        ):
            with self.subTest(correct_value=correct_value, ocr_value=ocr_value):
                result = self.build_result(
                    _delivery_block("PO", "po.pdf", correct_value),
                    _delivery_block("INVOICE", "invoice.pdf", ocr_value),
                )

                self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_province_name_with_ocr_typo_matches_known_province(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF HAI PHONG"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF HAI PHON"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_two_distinct_known_provinces_remain_mismatched_even_when_names_are_similar(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF SHANXI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF SHAANXI"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_trailing_incoterms_version_does_not_cause_mismatch(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF NOI BAI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF NOI BAI, INCOTERMS 2020"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_different_unknown_locations_do_not_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF NARITA AIRPORT"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF HANEDA AIRPORT"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
        self.assertEqual(
            result["criteria"]["Description"],
            (
                "Điều kiện giao hàng không khớp: "
                "Yêu cầu mua hàng (PO) = CIF NARITA AIRPORT; "
                "Hóa đơn (VAT) = CIF HANEDA AIRPORT."
            ),
        )

    def test_unknown_location_does_not_match_known_geography(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF NARITA AIRPORT"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF JAPAN"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_invoice_and_commercial_invoice_are_independent_groups(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice.pdf", "CIF HAIPHONG"),
            _delivery_block("COMMERCIAL INVOICE", "cinv.pdf", "CIF NOIBAI"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "invoice.pdf, cinv.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

    def test_minority_conflicting_location_still_returns_ng(self):
        result = self.build_result(
            _delivery_block("PO", "po-noise.pdf", "T/T"),
            _delivery_block("PO", "po-haiphong-1.pdf", "CIF HAIPHONG"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF HAIPHONG"),
            _delivery_block("PO", "po-noibai.pdf", "CIF NOIBAI"),
            _delivery_block("PO", "po-haiphong-2.pdf", "CIF HAI PHONG"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "po-haiphong-1.pdf, po-noibai.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

    def test_top_count_tie_is_ng_and_lists_normalized_terms(self):
        result = self.build_result(
            _delivery_block("PO", "po-haiphong.pdf", "CIF HAIPHONG"),
            _delivery_block("PO", "po-noibai.pdf", "CIF NOIBAI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF HAIPHONG"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "po-haiphong.pdf, po-noibai.pdf")
        self.assertIn("PO", criteria["Description"])
        self.assertIn(
            "có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau",
            criteria["Description"],
        )
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

    def test_bare_and_one_unknown_location_tie_is_one_condition(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
            _delivery_block("INVOICE", "invoice-meiko.pdf", "DDP MEIKO"),
            _delivery_block("PO", "po.pdf", "DDP"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "OK")
        self.assertNotIn(
            "có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau",
            criteria["Description"],
        )

    def test_bare_country_and_province_tie_is_one_condition(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
            _delivery_block("INVOICE", "invoice-japan.pdf", "DDP JAPAN"),
            _delivery_block("INVOICE", "invoice-tokyo.pdf", "DDP TOKYO"),
            _delivery_block("PO", "po.pdf", "DDP"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_country_conflict_in_tie_remains_ng(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice-japan.pdf", "DDP JAPAN"),
            _delivery_block("INVOICE", "invoice-vietnam.pdf", "DDP VIETNAM"),
            _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
            _delivery_block("PO", "po.pdf", "DDP"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(
            criteria["FileName"],
            "invoice-japan.pdf, invoice-vietnam.pdf, invoice-bare.pdf",
        )
        self.assertIn(
            "có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau",
            criteria["Description"],
        )

    def test_incoterm_and_country_conflict_in_tie_remains_ng(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice-japan.pdf", "DDP JAPAN"),
            _delivery_block("INVOICE", "invoice-vietnam.pdf", "CIF VIETNAM"),
            _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
            _delivery_block("PO", "po.pdf", "DDP"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(
            criteria["FileName"],
            "invoice-japan.pdf, invoice-vietnam.pdf, invoice-bare.pdf",
        )
        self.assertIn(
            "có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau",
            criteria["Description"],
        )

    def test_two_compatible_incoterm_groups_in_one_tie_remain_ng(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice-cif.pdf", "CIF"),
            _delivery_block("INVOICE", "invoice-ddp-japan.pdf", "DDP JAPAN"),
            _delivery_block("INVOICE", "invoice-cif-vietnam.pdf", "CIF VIETNAM"),
            _delivery_block("INVOICE", "invoice-ddp.pdf", "DDP"),
            _delivery_block("PO", "po.pdf", "DDP"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(
            criteria["FileName"],
            "invoice-cif.pdf, invoice-ddp-japan.pdf, invoice-cif-vietnam.pdf, invoice-ddp.pdf",
        )
        self.assertIn(
            "có nhiều điều kiện giao hàng xuất hiện với số lần bằng nhau",
            criteria["Description"],
        )

    def test_compatible_tie_selects_most_specific_representative(self):
        result = self.build_result(
            _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
            _delivery_block("INVOICE", "invoice-japan.pdf", "DDP JAPAN"),
            _delivery_block("INVOICE", "invoice-tokyo.pdf", "DDP TOKYO"),
            _delivery_block("PO", "po-osaka.pdf", "DDP OSAKA"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_two_by_two_tie_uses_earliest_non_empty_representative_per_value(self):
        result = self.build_result(
            _delivery_block("PO", "", "CIF HAIPHONG"),
            _delivery_block("PO", "hanoi-first.pdf", "CIF HANOI"),
            _delivery_block("PO", "haiphong-first.pdf", "CIF HAI PHONG"),
            _delivery_block("PO", "hanoi-second.pdf", "CIF HA NOI"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
        self.assertEqual(
            result["criteria"]["FileName"],
            "hanoi-first.pdf, haiphong-first.pdf",
        )

    def test_zero_valid_document_groups_is_blank_with_fallback_name(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "T/T"),
            _delivery_block("INVOICE", "invoice.pdf"),
            criterion_name="",
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaName"], "Điều kiện giao hàng")
        self.assertEqual(criteria["CriteriaStatus"], "BLANK")
        self.assertEqual(criteria["FileName"], "po.pdf, invoice.pdf")
        self.assertIn(
            "Không đủ ít nhất 2 loại chứng từ có điều kiện giao hàng hợp lệ để đối chiếu",
            criteria["Description"],
        )
        self.assertIn(
            "Yêu cầu mua hàng (PO): không có điều kiện giao hàng hợp lệ",
            criteria["Description"],
        )
        self.assertIn(
            "Hóa đơn (VAT): thiếu điều kiện giao hàng",
            criteria["Description"],
        )

    def test_one_valid_document_group_is_blank(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF TOKYO"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "PAYMENT TERM"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "BLANK")
        self.assertEqual(criteria["FileName"], "custom.xlsx")
        self.assertIn("Yêu cầu mua hàng (PO): hợp lệ", criteria["Description"])
        self.assertIn(
            "Tờ khai hải quan: không có điều kiện giao hàng hợp lệ",
            criteria["Description"],
        )


    def test_different_incoterms_do_not_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "FOB TOKYO"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF TOKYO"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_alias_equivalent_provinces_match(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF TOKYO-TO"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF 東京都"),
        )

        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_blank_filenames_are_deduplicated_source_ordered_and_capped_at_ten(self):
        blocks = [
            _delivery_block("PO", "invalid-01.pdf", "T/T"),
            _delivery_block("INVOICE", "invalid-02.pdf", "PAYMENT"),
            _delivery_block("PO", "invalid-01.pdf", "LC"),
        ]
        blocks.extend(
            _delivery_block("PO", f"invalid-{index:02d}.pdf", "NET 30")
            for index in range(3, 13)
        )

        result = self.build_result(*blocks)

        self.assertEqual(result["criteria"]["CriteriaStatus"], "BLANK")
        self.assertEqual(
            result["criteria"]["FileName"],
            ", ".join(f"invalid-{index:02d}.pdf" for index in range(1, 11)),
        )

    def test_incoterm_mismatch_outranks_province_and_location_mismatches(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF TOKYO"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF OSAKA"),
            _delivery_block("INVOICE", "invoice.pdf", "FOB TOKYO"),
            _delivery_block("COMMERCIAL INVOICE", "cinv.pdf", "CIF NARITA AIRPORT"),
        )

        self.assertCriteria(
            result,
            status="NG",
            file_name="po.pdf, invoice.pdf",
            description=(
                "Điều kiện giao hàng không khớp: Yêu cầu mua hàng (PO) = CIF TOKYO; "
                "Hóa đơn (VAT) = FOB TOKYO."
            ),
        )

    def test_country_mismatch_outranks_province_and_location_mismatches(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF TOKYO"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF OSAKA"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF VIETNAM"),
            _delivery_block("COMMERCIAL INVOICE", "cinv.pdf", "CIF NARITA AIRPORT"),
        )

        self.assertCriteria(
            result,
            status="NG",
            file_name="po.pdf, invoice.pdf",
            description=(
                "Điều kiện giao hàng không khớp: Yêu cầu mua hàng (PO) = CIF TOKYO; "
                "Hóa đơn (VAT) = CIF VIETNAM."
            ),
        )

    def test_same_priority_mismatch_uses_earliest_representative_pair(self):
        result = self.build_result(
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF OSAKA"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF KYOTO"),
            _delivery_block("PO", "po.pdf", "CIF TOKYO"),
        )

        self.assertCriteria(
            result,
            status="NG",
            file_name="custom.xlsx, invoice.pdf",
            description=(
                "Điều kiện giao hàng không khớp: Tờ khai hải quan = CIF OSAKA; "
                "Hóa đơn (VAT) = CIF KYOTO."
            ),
        )

    def test_large_tie_uses_one_representative_file_per_tied_value(self):
        blocks = []
        for index in range(1, 13):
            delivery_term = "CIF HAIPHONG" if index % 2 else "CIF HANOI"
            blocks.append(_delivery_block("PO", f"tie-{index:02d}.pdf", delivery_term))
        blocks.extend((
            _delivery_block("PO", "tie-01.pdf", "CIF HAI PHONG"),
            _delivery_block("PO", "tie-02.pdf", "CIF HA NOI"),
        ))

        result = self.build_result(*blocks)

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "tie-01.pdf, tie-02.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF HA NOI", criteria["Description"])

    def test_incoterm_mismatch_outranks_country_mismatch(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF JAPAN"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF VIETNAM"),
            _delivery_block("INVOICE", "invoice.pdf", "FOB JAPAN"),
        )

        self.assertCriteria(
            result,
            status="NG",
            file_name="po.pdf, invoice.pdf",
            description=(
                "Điều kiện giao hàng không khớp: Yêu cầu mua hàng (PO) = CIF JAPAN; "
                "Hóa đơn (VAT) = FOB JAPAN."
            ),
        )

    def test_province_mismatch_outranks_unknown_location_mismatch(self):
        result = self.build_result(
            _delivery_block("PO", "po.pdf", "CIF HAIPHONG"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF HANOI"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF NARITA AIRPORT"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "po.pdf, custom.xlsx")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF HA NOI", criteria["Description"])

    def test_representative_uses_earliest_non_empty_filename_for_winning_value(self):
        result = self.build_result(
            _delivery_block("PO", "", "CIF HAIPHONG"),
            _delivery_block("PO", "po.pdf", "CIF HAI PHONG"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF NOIBAI"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "po.pdf, invoice.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

    def test_borrowed_representative_filename_uses_its_actual_source_position(self):
        result = self.build_result(
            _delivery_block("PO", "", "CIF HAIPHONG"),
            _delivery_block("INVOICE", "invoice.pdf", "CIF NOIBAI"),
            _delivery_block("PO", "po.pdf", "CIF HAI PHONG"),
        )

        criteria = result["criteria"]
        self.assertEqual(criteria["CriteriaStatus"], "NG")
        self.assertEqual(criteria["FileName"], "invoice.pdf, po.pdf")
        self.assertIn("CIF HAI PHONG", criteria["Description"])
        self.assertIn("CIF NOI BAI", criteria["Description"])

class DeliveryTermOCRComparisonTests(unittest.TestCase):
    def test_spacing_variants_match_without_changing_source_values(self):
        for left, right in (("HANOI", "HA NOI"), ("NOIBAI", "NOI BAI"), ("HAIPHONG", "HAI PHONG")):
            with self.subTest(left=left, right=right):
                self.assertEqual(rules._delivery_term_location_key(left), rules._delivery_term_location_key(right))
                self.assertTrue(rules._delivery_term_location_matches(left, right))

    def test_ocr_character_variants_match_without_mutating_source(self):
        cases = (("HANOI", "HAN0I"), ("NOIBAI", "NOL BAI"), ("HAIPHONG", "HA1PHONG"))
        for expected, ocr_value in cases:
            with self.subTest(expected=expected, ocr_value=ocr_value):
                self.assertTrue(rules._delivery_term_location_matches(expected, ocr_value))
                self.assertNotEqual(expected, ocr_value)
                self.assertEqual(ocr_value, ocr_value)

    def test_ocr_aware_similarity_does_not_rewrite_values(self):
        original = "HAN0I"
        similarity = rules._delivery_term_ocr_aware_similarity("HANOI", original)
        self.assertGreaterEqual(similarity, rules.DELIVERY_TERM_LOCATION_SIMILARITY_THRESHOLD)
        self.assertEqual(original, "HAN0I")

    def test_extra_ocr_character_is_tolerated_when_similarity_is_high(self):
        self.assertTrue(rules._delivery_term_location_matches("HAI PHONG", "HAI PHONGX"))

    def test_different_locations_remain_mismatched(self):
        for left, right in (("HANOI", "HAIPHONG"), ("NOIBAI", "TANSONNHAT"), ("HAIPHONG", "DANANG")):
            with self.subTest(left=left, right=right):
                self.assertFalse(rules._delivery_term_location_matches(left, right))

    def test_delivery_term_result_accepts_common_ocr_location_variants(self):
        cases = (("CIF HANOI", "CIF HAN0I"), ("CIF NOIBAI", "CIF NOL BAI"), ("CIF HAI PHONG", "CIF HA1PHONG"))
        for expected, ocr_value in cases:
            with self.subTest(expected=expected, ocr_value=ocr_value):
                result = rules._build_delivery_term_result(
                    _delivery_block("PO", "po.pdf", expected) + "\n" + _delivery_block("INVOICE", "invoice.pdf", ocr_value),
                    "?i?u ki?n giao h?ng",
                )
                self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")


class DeliveryTermIntegrationTests(unittest.TestCase):
    criterion_name = "Dieu kien giao hang"

    class Logger:
        def warning(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

    def build_prompt(self, *, dntt_type, formation_id, installment="", content=""):
        directive = {
            "PromptType": "DOICHIEU",
            "DnttType": dntt_type,
            "FormationID": formation_id,
            "Installment": installment,
            "CriterionName": self.criterion_name,
        }
        return "***\n" + json.dumps(directive) + "\n***\n" + content

    def run_process(self, latest_user, generate_with_trim_fn):
        response_logs = []
        cleanup_calls = []
        with TemporaryDirectory() as temp_dir:
            result, status_code = rules.process_ai_llms_models_rules(
                latest_system="",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                data_holidays_dir=Path("App/Data_Holidays"),
                split_ocr_text_fn=lambda **kwargs: [],
                generate_with_trim_fn=generate_with_trim_fn,
                append_response_log_fn=response_logs.append,
                light_cuda_cleanup_fn=lambda: cleanup_calls.append(True),
                logger=self.Logger(),
            )
        return result, status_code, response_logs, cleanup_calls

    def fail_if_llm_called(self, **kwargs):
        raise AssertionError("delivery-term integration must not call the LLM")

    def compatible_content(self):
        return "\n".join((
            _delivery_block("PO", "po.pdf", "CIF TOKYO"),
            _delivery_block("CUSTOMSHEET", "custom.xlsx", "CIF JAPAN"),
            _delivery_block("COMMERCIALINVOICE", "invoice.pdf", "CIF TOKYO-TO"),
        ))

    def compatible_result(self):
        return {
            "criteria": {
                "CriteriaName": self.criterion_name,
                "CriteriaStatus": "OK",
                "FileName": "",
                "Description": "\u0110i\u1ec1u ki\u1ec7n giao h\u00e0ng \u0111\u00e3 ho\u00e0n to\u00e0n kh\u1edbp v\u1edbi nhau.",
            }
        }

    def test_nguyenvatlieu_kethua_blank_installment_returns_exact_result_without_llm(self):
        result, status_code, response_logs, cleanup_calls = self.run_process(
            self.build_prompt(
                dntt_type="NGUYENVATLIEU",
                formation_id="KETHUA_CONGNO",
                content=self.compatible_content(),
            ),
            self.fail_if_llm_called,
        )

        expected = self.compatible_result()
        self.assertEqual(result, expected)
        self.assertEqual(status_code, 200)
        self.assertEqual(response_logs, [expected])
        self.assertEqual(cleanup_calls, [True])

    def test_nguyenvatlieu_kethua_phieucongtac_uses_delivery_logic_without_llm(self):
        content = "\n".join((
            _delivery_block("CUSTOMSHEET", "ToKhaiHQ7N_QDTQ_108236239530.xls", "CIF"),
            _delivery_block("INVOICE", "IV_2603-32.pdf", "CIF HAIPHONG"),
            _delivery_block("CUSTOMSHEET", "ToKhaiHQ7N_QDTQ_108305059550.xls", "CIF"),
            _delivery_block("INVOICE", "IV_-2603-33.pdf", "CIF HAIPHONG"),
            _delivery_block("CUSTOMSHEET", "ToKhaiHQ7N_QDTQ_108326365450.xls", "CIF"),
            _delivery_block("INVOICE", "IV_2604-10.pdf", "CIF HAIPHONG"),
            _delivery_block("PO", "PO_VB33-26020003-RV.pdf", "CIF HAIPHONG"),
            _delivery_block("PO", "PO_VB33-26020002-RV.pdf", "CIF HAIPHONG"),
            _delivery_block("PO", "PO_VB33-26020004-RV.pdf", "CIF HAIPHONG"),
        ))

        result, status_code, response_logs, cleanup_calls = self.run_process(
            self.build_prompt(
                dntt_type="NGUYENVATLIEU",
                formation_id="KETHUA_PHIEUCONGTAC",
                content=content,
            ),
            self.fail_if_llm_called,
        )

        expected = self.compatible_result()
        self.assertEqual(result, expected)
        self.assertEqual(status_code, 200)
        self.assertEqual(response_logs, [expected])
        self.assertEqual(cleanup_calls, [True])

    def test_nguyenvatlieu_one_valid_document_returns_blank_before_missing_guards(self):
        result, status_code, response_logs, cleanup_calls = self.run_process(
            self.build_prompt(
                dntt_type="NGUYENVATLIEU",
                formation_id="KETHUA_CONGNO",
                content=_delivery_block("PO", "po.pdf", "CIF TOKYO"),
            ),
            self.fail_if_llm_called,
        )

        expected = {
            "criteria": {
                "CriteriaName": self.criterion_name,
                "CriteriaStatus": "BLANK",
                "FileName": "",
                "Description": (
                    "Không đủ ít nhất 2 loại chứng từ có điều kiện giao hàng hợp lệ "
                    "để đối chiếu. Yêu cầu mua hàng (PO): hợp lệ; "
                    "Tờ khai hải quan: không có chứng từ; "
                    "Hóa đơn (VAT): không có chứng từ; "
                    "Hóa đơn thương mại: không có chứng từ."
                ),
            }
        }
        self.assertEqual(result, expected)
        self.assertEqual(status_code, 200)
        self.assertEqual(response_logs, [expected])
        self.assertEqual(cleanup_calls, [True])

    def test_maymoc_kethua_default_installment_returns_exact_result_without_llm(self):
        result, status_code, response_logs, cleanup_calls = self.run_process(
            self.build_prompt(
                dntt_type="MAYMOC",
                formation_id="KETHUA_CONGNO",
                content=self.compatible_content(),
            ),
            self.fail_if_llm_called,
        )

        expected = self.compatible_result()
        self.assertEqual(result, expected)
        self.assertEqual(status_code, 200)
        self.assertEqual(response_logs, [expected])
        self.assertEqual(cleanup_calls, [True])

    def test_maymoc_datcoc_skip_compare_still_wins_over_specialized_builder(self):
        with patch.object(
            rules,
            "_build_delivery_term_result",
            side_effect=AssertionError("skip_compare must remain authoritative"),
        ):
            result, status_code, response_logs, cleanup_calls = self.run_process(
                self.build_prompt(
                    dntt_type="MAYMOC",
                    formation_id="DATCOC_TRATRUOC",
                    content=self.compatible_content(),
                ),
                self.fail_if_llm_called,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["criteria"]["CriteriaName"], self.criterion_name)
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        self.assertEqual(result["criteria"]["FileName"], "")
        self.assertIn("b\u1ecf qua khi so s\u00e1nh", result["criteria"]["Description"])
        self.assertEqual(response_logs, [result])
        self.assertEqual(cleanup_calls, [True])

    def test_out_of_scope_dossier_keeps_existing_llm_flow_once(self):
        llm_calls = []
        expected = {
            "criteria": {
                "CriteriaName": self.criterion_name,
                "CriteriaStatus": "NG",
                "FileName": "outside.pdf",
                "Description": "controlled fallback result",
            }
        }

        def generate_with_trim_fn(**kwargs):
            llm_calls.append(kwargs)
            return json.dumps(expected)

        result, status_code, response_logs, cleanup_calls = self.run_process(
            self.build_prompt(
                dntt_type="OUT_OF_SCOPE",
                formation_id="KETHUA_CONGNO",
                content=_delivery_block("PO", "outside.pdf", "CIF TOKYO"),
            ),
            generate_with_trim_fn,
        )

        self.assertEqual(result, expected)
        self.assertEqual(status_code, 200)
        self.assertEqual(len(llm_calls), 1)
        self.assertEqual(response_logs, [expected])
        self.assertEqual(cleanup_calls, [True])


if __name__ == "__main__":
    unittest.main()
