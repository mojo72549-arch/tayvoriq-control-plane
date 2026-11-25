import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import tayvoriq_provider_quota_diagnostic as diagnostic

SID='20261125-evening-agentv2-c28654554'

class QuotaDiagnosticTests(unittest.TestCase):
    def test_quota_error_is_allowlisted_and_excludes_messages_project_ids_and_credentials(self):
        payload={'error':{'message':'private-project api-key-secret','details':[
            {'@type':'type.googleapis.com/google.rpc.QuotaFailure','violations':[{'quotaMetric':'generativelanguage.googleapis.com/generate_content_free_tier_requests','quotaId':'GenerateRequestsPerDayPerProjectPerModel-FreeTier','quotaValue':'20','quotaDimensions':{'project':'private-project'}}]},
            {'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'42.5s'}]}}
        result=diagnostic.quota_details(payload)
        self.assertEqual(result['tier_hint'],'free');self.assertEqual(result['quota_metrics'][0]['kind'],'daily')
        self.assertEqual(result['quota_metrics'][0]['limit'],20);self.assertEqual(result['retry_after_seconds'],42.5)
        self.assertNotIn('private-project',json.dumps(result));self.assertNotIn('api-key-secret',json.dumps(result))

    def test_exactly_one_request_is_bounded_and_the_response_does_not_echo_credentials_or_generated_text(self):
        control={'schema':'tayvoriq-provider-quota-diagnostic-request-v1','selection_id':SID,'requested_at_epoch':1000}
        error={'error':{'message':'do not publish this','details':[]}}
        request=Mock(side_effect=HTTPError('https://example.test',429,'quota',{},io.BytesIO(json.dumps(error).encode())))
        result=diagnostic.diagnose(control,{'selection_id':SID},env={'GEMINI_API_KEY':'secret-test-key'},clock=lambda:1001,request=request)
        self.assertEqual(request.call_count,1);self.assertEqual(result['http_status'],429)
        self.assertEqual(json.loads(request.call_args.args[0].data)['generationConfig']['maxOutputTokens'],64)
        self.assertNotIn('secret-test-key',json.dumps(result));self.assertNotIn('do not publish',json.dumps(result))

    def test_an_expired_or_superseded_request_performs_no_provider_call(self):
        control={'schema':'tayvoriq-provider-quota-diagnostic-request-v1','selection_id':SID,'requested_at_epoch':1000}
        for owner,clock in [({'selection_id':'other'},1001),({'selection_id':SID},1400)]:
            request=Mock();result=diagnostic.diagnose(control,owner,env={'GEMINI_API_KEY':'secret'},clock=lambda:clock,request=request)
            self.assertEqual(result['calls'],0);request.assert_not_called()
