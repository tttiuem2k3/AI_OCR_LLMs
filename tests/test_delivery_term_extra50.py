import unittest
import App.Rules_AI_BEM_MEIKO as rules


def block(doc_type, name, term=None):
    fields = [f"Loai chung tu: {doc_type}", f"File Name: {name}"]
    if term is not None:
        fields.append(f"Dieu kien giao hang: {term}")
    return "{ " + " | ".join(fields) + " }"


def build(*docs):
    content = "\n".join(block(*d) for d in docs)
    return rules._build_delivery_term_result(content, "Điều kiện giao hàng")


CASES = [
    ([('PO','po','FOB HANOI'),('INVOICE','inv','FOB HA NOI')], 'OK'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF NOI BAI')], 'OK'),
    ([('PO','po','FOB HAIPHONG'),('INVOICE','inv','FOB HAI PHONG')], 'OK'),
    ([('PO','po','CIF HANOI'),('INVOICE','inv','CIF HAN0I')], 'OK'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF NOL BAI')], 'OK'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF NOIBA1')], 'OK'),
    ([('PO','po','FOB HAI PHONG'),('INVOICE','inv','FOB HA1 PH0NG')], 'OK'),
    ([('PO','po','CIF HO CHI MINH'),('INVOICE','inv','CIF H0CH1MINH')], 'OK'),
    ([('PO','po','FOB TAN SON NHAT'),('INVOICE','inv','FOB TANSONNHAT')], 'OK'),
    ([('PO','po','CIP NOI BAI'),('INVOICE','inv','CIP NOIBAI(HANOI)')], 'OK'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF NOIBAL')], 'OK'),
    ([('PO','po','CIF ABCDE'),('INVOICE','inv','CIF ABCDF')], 'OK'),
    ([('PO','po','CIF NARITA AIRPORT'),('INVOICE','inv','CIF NARITA AIRPORT')], 'OK'),
    ([('PO','po','FCA SINGAPORE'),('INVOICE','inv','FCA LOYANG DC')], 'OK'),
    ([('PO','po','FCA SINGAPORE'),('INVOICE','inv','FCA CHANGI BUSINESS PARK')], 'OK'),
    ([('PO','po','CIF JAPAN'),('INVOICE','inv','CIF TOKYO')], 'OK'),
    ([('PO','po','CIF VIETNAM'),('INVOICE','inv','CIF HAI PHONG')], 'OK'),
    ([('PO','po','CIF HAI PHONG'),('INVOICE','inv','CIF VIETNAM HAIPHONG')], 'OK'),
    ([('PO','po','CIP NOIBAI'),('INVOICE','inv','CIP HA NOI')], 'OK'),
    ([('PO','po','FOB HAI-PHONG'),('INVOICE','inv','FOB HAI PHONG')], 'OK'),
    ([('PO','po','FOB HAI PHONG'),('INVOICE','inv','FOB HAI PHONG'),('CUSTOMSHEET','cus','FOB HA1 PH0NG')], 'OK'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF NOI BAI'),('CUSTOMSHEET','cus','CIF NOLBAI')], 'OK'),
    ([('PO','po','CIF HANOI'),('INVOICE','inv','CIF HA NOI'),('CUSTOMSHEET','cus','CIF HAN0I'),('COMMERCIAL INVOICE','ci','CIF HANOI')], 'OK'),
    ([('PO','po','FOB HAI PHONG'),('INVOICE','inv','FOB HAIPHONG'),('CUSTOMSHEET','cus','FOB HAI PHONG'),('COMMERCIAL INVOICE','ci','FOB HA1 PH0NG')], 'OK'),
    ([('PO','po','CIF HAI PHONG'),('INVOICE','inv','CIF HAI PHONG'),('CUSTOMSHEET','cus','CIF HANOI')], 'NG'),
    ([('PO','po','FOB HAI PHONG'),('INVOICE','inv','CIF HAI PHONG')], 'NG'),
    ([('PO','po','FOB VIETNAM'),('INVOICE','inv','FOB JAPAN')], 'NG'),
    ([('PO','po','FOB HANOI'),('INVOICE','inv','FOB HAIPHONG')], 'NG'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF TAN SON NHAT')], 'NG'),
    ([('PO','po','FCA JURONG'),('INVOICE','inv','FCA TUAS')], 'NG'),
    ([('PO','po','CIF HANOI'),('INVOICE','inv','CIF DANANG')], 'NG'),
    ([('PO','po','CIF CHINA'),('INVOICE','inv','CIF JAPAN')], 'NG'),
    ([('PO','po','CIF'),('INVOICE','inv','FOB')], 'NG'),
    ([('PO','po','CIF HAI PHONG'),('INVOICE','inv','CIF HAI PHONG'),('CUSTOMSHEET','cus','CIF HAI PHONG'),('COMMERCIAL INVOICE','ci','CIP HAI PHONG')], 'NG'),
    ([('PO','po','CIF HANOI'),('INVOICE','inv','CIF HAN0I'),('CUSTOMSHEET','cus','CIF HAIPHONG')], 'NG'),
    ([('PO','po','CIF NOIBAI'),('INVOICE','inv','CIF NOLBAI'),('CUSTOMSHEET','cus','CIF TAN SON NHAT')], 'NG'),
    ([('PO','po','CIF HAI PHONG'),('INVOICE','inv','CIF HA1 PH0NG'),('CUSTOMSHEET','cus','CIF HANOI')], 'NG'),
    ([('PO','po','CIF HANOI')], 'BLANK'),
    ([('PO','po',None),('INVOICE','inv',None)], 'BLANK'),
    ([('PO','po',''),('INVOICE','inv','')], 'BLANK'),
    ([('PO','po','CIF HANOI'),('INVOICE','inv',None)], 'BLANK'),
    ([('PO','po','CIF'),('INVOICE','inv','CIF')], 'OK'),
    ([('PO','po','FOB'),('INVOICE','inv','FOB'),('CUSTOMSHEET','cus','FOB')], 'OK'),
    ([('PO','po','EX WORKS VIETNAM'),('INVOICE','inv','EXW VIETNAM')], 'OK'),
    ([('PO','po','FREE ON BOARD HAI PHONG'),('INVOICE','inv','FOB HAI PHONG')], 'OK'),
    ([('PO','po','COST INSURANCE FREIGHT VIETNAM'),('INVOICE','inv','CIF VIETNAM')], 'OK'),
    ([('PO','po','DELIVERED AT PLACE VIETNAM'),('INVOICE','inv','DAP VIETNAM')], 'OK'),
    ([('PO','po','FOB NOIBAI'),('INVOICE','inv','FOB NOI BAI'),('CUSTOMSHEET','cus','FOB HANOI')], 'OK'),
    ([('PO','po','FOB HAI PHONG'),('INVOICE','inv','FOB HA1 PH0NG'),('CUSTOMSHEET','cus','FOB HAIPHONG')], 'OK'),
    ([('PO','po','CIF HANOI'),('INVOICE','inv','CIF HAN0I'),('CUSTOMSHEET','cus','CIF HANOI'),('COMMERCIAL INVOICE','ci','CIF HAIPHONG')], 'NG'),
]


class Extra50DeliveryTermTests(unittest.TestCase):
    pass


def _make_test(index, docs, expected):
    def test(self):
        result = build(*docs)
        self.assertEqual(result['criteria']['CriteriaStatus'], expected, msg=f"TC{index:02d}: {docs}")
    test.__name__ = f"test_extra_{index:02d}"
    return test


for _i, (_docs, _expected) in enumerate(CASES, 1):
    setattr(Extra50DeliveryTermTests, f"test_extra_{_i:02d}", _make_test(_i, _docs, _expected))


if __name__ == '__main__':
    unittest.main()
