import pytest
from django.utils import timezone

from collectors.framework.models import CollectorMetadata
from collectors.nvd.collectors import NVDCollector
from osidb.models import Flaw, FlawCVSS
from osidb.tests.factories import FlawCVSSFactory, FlawFactory

pytestmark = pytest.mark.integration


class TestNVDCollector:
    """
    NVDCollector test cases
    """

    @pytest.mark.vcr
    def test_collect_batch(self):
        """
        test that collecting a batch of CVEs works
        """
        # let us use existing CVE data as a real-world example
        # https://services.nvd.nist.gov/rest/json/cves/2.0/?lastModStartDate=2010-01-01T00:00:00&lastModEndDate=2010-04-11T00:00:00

        nvdc = NVDCollector()
        nvdc.metadata.updated_until_dt = timezone.datetime(
            2010, 1, 1, 0, 0, tzinfo=timezone.utc
        )

        # test that the batch is correctly selected
        batch, period_end = nvdc.get_batch()
        assert len(batch) == 300
        assert period_end == timezone.datetime(2010, 4, 11, 0, 0, tzinfo=timezone.utc)

        # test that the batch collection works
        # randomly select a few flaws - not all 300
        #
        # we do not test CVSS3 as these old flaws do not have it
        # but more recent batches are too huge (a few MB cassettes)
        # it is going to be tested by another test case
        FlawFactory(
            cve_id="CVE-2000-0835",
            nvd_cvss2=None,
        )
        FlawFactory(
            cve_id="CVE-2010-0977",
            nvd_cvss2=None,
        )
        FlawFactory(
            cve_id="CVE-2010-1313",
            nvd_cvss2=None,
        )

        nvdc.collect()

        flaw = Flaw.objects.get(cve_id="CVE-2000-0835")
        assert flaw.nvd_cvss2 == "5.0/AV:N/AC:L/Au:N/C:P/I:N/A:N"

        flaw = Flaw.objects.get(cve_id="CVE-2010-0977")
        assert flaw.nvd_cvss2 == "5.0/AV:N/AC:L/Au:N/C:P/I:N/A:N"

        flaw = Flaw.objects.get(cve_id="CVE-2010-1313")
        assert flaw.nvd_cvss2 == "4.3/AV:N/AC:M/Au:N/C:P/I:N/A:N"

    @pytest.mark.vcr
    def test_collect_cve(self):
        """
        test that collecting a given CVE works
        """
        # let us use existing CVE data as a real-world example
        # https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2020-1234
        cve = "CVE-2020-1234"

        FlawFactory(
            cve_id=cve,
            nvd_cvss2=None,
            nvd_cvss3=None,
        )

        nvdc = NVDCollector()
        nvdc.collect(cve)

        flaw = Flaw.objects.first()
        assert flaw.cve_id == cve
        assert flaw.nvd_cvss2 == "6.8/AV:N/AC:M/Au:N/C:P/I:P/A:P"
        assert flaw.nvd_cvss3 == "7.8/CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"

    @pytest.mark.vcr
    def test_collect_updated(self):
        """
        test that collecting updated CVE works
        """
        # let us use existing CVE data as a real-world examples
        # https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2020-1234
        cve1 = "CVE-2020-1234"
        # https://services.nvd.nist.gov/rest/json/cves/2.0?cveId=CVE-2020-1235
        cve2 = "CVE-2020-1235"

        # let us define a time of last collection
        # and one timestamp before and one after
        before_collector_run = timezone.datetime(2022, 1, 1, 0, 0, tzinfo=timezone.utc)
        last_collector_run = timezone.datetime(2022, 2, 1, 0, 0, tzinfo=timezone.utc)
        after_collector_run = timezone.datetime(2022, 3, 1, 0, 0, tzinfo=timezone.utc)

        FlawFactory(
            cve_id=cve1,
            nvd_cvss2=None,
            nvd_cvss3=None,
            updated_dt=before_collector_run,
        )
        FlawFactory(
            cve_id=cve2,
            nvd_cvss2=None,
            nvd_cvss3=None,
            updated_dt=after_collector_run,
        )

        nvdc = NVDCollector()
        nvdc.metadata.updated_until_dt = last_collector_run
        # no change should happen when not complete
        nvdc.collect_updated()

        flaw = Flaw.objects.get(cve_id=cve1)
        assert not flaw.nvd_cvss2
        assert not flaw.nvd_cvss3

        flaw = Flaw.objects.get(cve_id=cve2)
        assert not flaw.nvd_cvss2
        assert not flaw.nvd_cvss3

        # make data complete
        nvdc.metadata.data_state = CollectorMetadata.DataState.COMPLETE
        nvdc.collect_updated()

        # first CVE was not updated after the
        # collector run so should be unchanged
        flaw = Flaw.objects.get(cve_id=cve1)
        assert not flaw.nvd_cvss2
        assert not flaw.nvd_cvss3

        flaw = Flaw.objects.get(cve_id=cve2)
        assert flaw.nvd_cvss2 == "6.8/AV:N/AC:M/Au:N/C:P/I:P/A:P"
        assert flaw.nvd_cvss3 == "7.8/CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"

    @pytest.mark.vcr
    @pytest.mark.enable_signals
    @pytest.mark.parametrize(
        "cve_id,original_cvss2,original_cvss3,new_cvss2,new_cvss3",
        [
            # without changes
            (
                "CVE-2014-0148",
                [None, None],
                [5.5, "CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H"],
                [None, None],
                [5.5, "CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H"],
            ),
            (
                "CVE-2020-1234",
                [6.8, "AV:N/AC:M/Au:N/C:P/I:P/A:P"],
                [7.8, "CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"],
                [6.8, "AV:N/AC:M/Au:N/C:P/I:P/A:P"],
                [7.8, "CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"],
            ),
            # new CVSSv2
            (
                "CVE-2000-0835",
                [None, None],
                [None, None],
                [5.0, "AV:N/AC:L/Au:N/C:P/I:N/A:N"],
                [None, None],
            ),
            # different CVSSv3
            (
                "CVE-2020-1235",
                [6.8, "AV:N/AC:M/Au:N/C:P/I:P/A:P"],
                [7.4, "CVSS:3.1/AV:L/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H"],
                [6.8, "AV:N/AC:M/Au:N/C:P/I:P/A:P"],
                [7.8, "CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:H/I:H/A:H"],
            ),
        ],
    )
    def test_flawcvss_model(
        self, cve_id, original_cvss2, original_cvss3, new_cvss2, new_cvss3
    ):
        """
        Test that CVSSv2 and CVSSv3 scores are correctly loaded and updated
        in the FlawCVSS model.
        """
        # do not care about nvd_cvss2 and nvd_cvss3 as they will be deprecated
        flaw = FlawFactory(cve_id=cve_id, nvd_cvss2="", nvd_cvss3="")

        for vector, version in [
            (original_cvss2[1], FlawCVSS.CVSSVersion.VERSION2),
            (original_cvss3[1], FlawCVSS.CVSSVersion.VERSION3),
        ]:
            if vector:
                FlawCVSSFactory(
                    flaw=flaw,
                    issuer=FlawCVSS.CVSSIssuer.NIST,
                    version=version,
                    vector=vector,
                )

        nvdc = NVDCollector()
        nvdc.collect(cve_id)

        flaw = Flaw.objects.get(cve_id=cve_id)

        for score, vector, version in [
            (new_cvss2[0], new_cvss2[1], FlawCVSS.CVSSVersion.VERSION2),
            (new_cvss3[0], new_cvss3[1], FlawCVSS.CVSSVersion.VERSION3),
        ]:
            if vector:
                assert flaw.cvss_scores.filter(version=version).first().score == score
                assert flaw.cvss_scores.filter(version=version).first().vector == vector
            else:
                assert flaw.cvss_scores.filter(version=version).first() is None
