"""Site-independent tests for slot collection, knowledge scoping and task boundaries."""
import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ai_workplace.advanced_conversation import extract_leave_slots, applicable_metadata, leave_request
from ai_workplace.conversation_guidance import guidance_category
from ai_workplace.services import conversation_engagement as backend
from ai_workplace.whatsapp.outbound import OutboundMessage


class Doc(dict):
    def __getattr__(self,key):
        return self.get(key)
    def __setattr__(self,key,value):
        self[key]=value
    def update(self,*args,**kwargs):
        super().update(*args,**kwargs)
        return self
    def db_set(self,values,**kwargs):
        self.update(values)
    def save(self,**kwargs):
        self.setdefault('name','T1')
        return self
    def insert(self,**kwargs):
        return self.save()


class TestSlotsAndScopes(unittest.TestCase):
    def setUp(self):
        self.today=date(2026,11,2)

    def test_one_message_collects_explicit_fields(self):
        slots=extract_leave_slots('Apply for annual leave from 2026-11-10 to 2026-11-12 full days because family trip',self.today)
        self.assertEqual(slots,dict(custom_leave_reason='Vacations',from_date='2026-11-10',to_date='2026-11-12',half_day=0,description='family trip'))

    def test_relative_day_uses_supplied_site_date(self):
        slots=extract_leave_slots('need sick leave tomorrow half day because appointment',self.today)
        self.assertEqual(slots['from_date'],'2026-11-03')
        self.assertEqual(slots['to_date'],'2026-11-03')
        self.assertEqual(slots['half_day'],1)

    def test_shared_month_range_is_extracted(self):
        slots=extract_leave_slots('annual leave from 10th to 12th November 2026',self.today)
        self.assertEqual(slots['from_date'],'2026-11-10')
        self.assertEqual(slots['to_date'],'2026-11-12')

    def test_month_before_day(self):
        slots=extract_leave_slots('annual leave from November 10, 2026 to November 12, 2026',self.today)
        self.assertEqual(slots['to_date'],'2026-11-12')

    def test_not_half_day_is_full_day(self):
        self.assertEqual(extract_leave_slots('annual leave tomorrow not half day',self.today)['half_day'],0)

    def test_free_text_reason_does_not_override_requested_type(self):
        slots=extract_leave_slots('annual leave tomorrow because my child is sick',self.today)
        self.assertEqual(slots['custom_leave_reason'],'Vacations')

    def test_missing_fields_are_not_guessed(self):
        slots=extract_leave_slots('Apply for leave',self.today)
        self.assertEqual(slots,{})

    def test_invalid_dates_are_not_silently_replaced(self):
        for text in ['from 2026-11-10 to 2026-11-99','from 2026-11-12 to 2026-11-10']:
            slots=extract_leave_slots(text,self.today)
            self.assertNotIn('to_date',slots)

    def test_incomplete_range_does_not_become_single_day(self):
        slots=extract_leave_slots('from 2026-11-10 to sometime next week',self.today)
        self.assertEqual(slots['from_date'],'2026-11-10')
        self.assertNotIn('to_date',slots)

    def test_past_dates_require_clarification(self):
        self.assertNotIn('from_date',extract_leave_slots('annual leave on 2026-10-01',self.today))

    def test_named_month_and_year(self):
        slots=extract_leave_slots('annual leave from 10 November 2026 to 12 November 2026',self.today)
        self.assertEqual(slots['to_date'],'2026-11-12')

    def test_family_sickness_does_not_become_self_sickness(self):
        self.assertEqual(extract_leave_slots('sick leave for my child tomorrow',self.today)['custom_leave_reason'],'Sick Leave Immediate Family')

    def test_request_detection_does_not_capture_balance_question(self):
        self.assertTrue(leave_request('I need annual leave tomorrow'))
        self.assertFalse(leave_request('What is my leave balance?'))

    def test_missing_department_fails_closed(self):
        self.assertFalse(applicable_metadata({'target_department':'HR'}, {}, self.today))
        self.assertTrue(applicable_metadata({'target_department':'HR'}, {'department':'HR'}, self.today))

    def test_unscoped_content_is_public_to_allowed_retrieval(self):
        self.assertTrue(applicable_metadata({'target_employment_type':'All'}, {}, self.today))

    def test_expired_and_future_policies_are_filtered(self):
        for chunk in [{'effective_date':'2026-11-03'},{'effective_to':'2026-11-01'},{'effective_to':'invalid'}]:
            self.assertFalse(applicable_metadata(chunk,{},self.today))
        self.assertTrue(applicable_metadata({'effective_to':'2026-11-02'}, {}, self.today))

    def test_categories_cover_supported_read_services(self):
        for intent,expected in [('leave_balance','leave'),('monthly_attendance','attendance'),('latest_salary_slip','payroll'),('employee_city_dsa','travel'),('my_profile','profile'),('careers','careers'),('onboarding','onboarding'),('documents','documents')]:
            self.assertEqual(guidance_category(intent),expected)


class TestBackend(unittest.TestCase):
    def setUp(self):
        self.frappe=MagicMock()
        self.now=datetime(2026,11,2,12)
        self.frappe.utils.now_datetime.return_value=self.now
        self.frappe.utils.get_datetime.side_effect=lambda value: value
        self.frappe.utils.get_system_timezone.return_value='Asia/Karachi'
        self.frappe.db.exists.return_value=True
        self.patch=patch.dict('sys.modules',{'frappe':self.frappe})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.context=dict(employee='E1',user='user@example.com',allowed_services=['attendance_leave'])
        self.conv=Doc(name='C1',employee='E1',erp_user='user@example.com',whatsapp_identity='I1',wa_id='923001234567',current_state='PROCESSING',current_intent='leave_apply',active_service='attendance_leave',last_message_id='M1',draft_payload=json.dumps({'step':'awaiting_confirm','description':'private reason'}),guidance_memory=json.dumps({'topic':'leave application','status':'awaiting_user','question':'Review and submit?'}))
        self.task=Doc(name='T1',**backend._owner_filters(self.conv,self.context),conversation='C0',topic='leave application',intent='leave_apply',active_service='attendance_leave',state='PROCESSING',status='Paused',expires_at=self.now+timedelta(days=1),draft_payload=self.conv.draft_payload,guidance_payload=self.conv.guidance_memory,question='Review and submit?')

    def test_disabled_account_blocks_reminders_across_conversations(self):
        self.frappe.db.get_value.return_value={'reminders_enabled':0}
        self.assertFalse(backend.reminders_allowed('user@example.com'))

    def test_no_preference_preserves_site_control(self):
        self.frappe.db.get_value.return_value=None
        self.assertTrue(backend.reminders_allowed('user@example.com'))

    def test_disable_preference_cancels_all_account_pending_work(self):
        self.frappe.db.get_value.return_value=None
        self.frappe.new_doc.return_value=Doc()
        value=backend.save_preference('user@example.com',False,20,9,'Asia/Karachi')
        self.assertEqual(value['reminders_enabled'],0)
        self.assertEqual(self.frappe.db.set_value.call_args.args[1]['erp_user'],'user@example.com')

    def test_pause_retains_private_draft_only_in_owned_task(self):
        self.frappe.db.get_value.return_value=None
        doc=Doc()
        self.frappe.new_doc.return_value=doc
        self.frappe.get_all.return_value=[]
        name=backend.pause_task(self.conv,self.context)
        self.assertEqual(name,'T1')
        self.assertEqual(doc.erp_user,'user@example.com')
        self.assertEqual(doc.draft_payload,self.conv.draft_payload)
        backend.detach(self.conv)
        self.assertIsNone(self.conv.draft_payload)
        self.assertIsNone(self.conv.current_intent)

    def test_pin_and_human_work_are_never_snapshotted(self):
        for state in ['WAITING_FOR_SUPPORT_PIN','LIVE_HR_CHAT','HR_GUEST_INTAKE']:
            self.conv.current_state=state
            self.assertIsNone(backend.pause_task(self.conv,self.context))

    def test_task_list_is_scoped_to_identity_employee_user_and_channel(self):
        self.frappe.get_all.return_value=[]
        handled,_=backend.task_control(self.conv,self.context,'my tasks')
        self.assertTrue(handled)
        filters=self.frappe.get_all.call_args.kwargs['filters']
        for key in ['erp_user','employee','whatsapp_identity','channel']:
            self.assertEqual(filters[key],backend._owner_filters(self.conv,self.context)[key])

    def test_resume_rechecks_current_authorization(self):
        self.frappe.get_all.return_value=[self.task]
        self.frappe.get_doc.return_value=self.task
        authorize=MagicMock(return_value={'allowed':False})
        with patch.dict('sys.modules',{'ai_workplace.auth.gateway':SimpleNamespace(authorize=authorize)}):
            _,out=backend.task_control(self.conv,self.context,'resume 1')
        self.assertIn('no longer have access',out.body_text)
        self.assertEqual(self.task.status,'Paused')

    def test_changed_task_owner_is_rejected_after_row_lock(self):
        self.frappe.get_all.return_value=[self.task]
        self.task.employee='E2'
        self.frappe.get_doc.return_value=self.task
        _,out=backend.task_control(self.conv,self.context,'resume 1')
        self.assertIn('no longer available',out.body_text)

    def test_expired_task_cannot_be_restored(self):
        self.frappe.get_all.return_value=[self.task]
        self.task.expires_at=self.now-timedelta(seconds=1)
        self.frappe.get_doc.return_value=self.task
        _,out=backend.task_control(self.conv,self.context,'resume 1')
        self.assertIn('no longer available',out.body_text)

    def test_resume_stops_at_confirmation_without_submitting(self):
        self.conv.current_intent=None
        self.frappe.get_all.return_value=[self.task]
        self.frappe.get_doc.return_value=self.task
        resume=MagicMock(return_value=OutboundMessage(body_text='Review and submit?'))
        modules={'ai_workplace.auth.gateway':SimpleNamespace(authorize=lambda *a,**k:{'allowed':True}),
                 'ai_workplace.security.authorization':SimpleNamespace(requires_pin=lambda _:False),
                 'ai_workplace.services.leave_apply':SimpleNamespace(resume_leave_prompt=resume)}
        with patch.dict('sys.modules',modules):
            handled,out=backend.task_control(self.conv,self.context,'resume leave')
        self.assertTrue(handled)
        self.assertEqual(out.body_text,'Review and submit?')
        self.assertEqual(self.conv.current_intent,'leave_apply')
        self.assertEqual(self.task.status,'Resumed')
        resume.assert_called_once()

    def test_analytics_failure_does_not_break_response(self):
        self.frappe.new_doc.side_effect=RuntimeError('optional metrics unavailable')
        self.frappe.db.exists.side_effect=lambda dt,value: dt=='DocType'
        backend.event(self.conv,'question','leave application')
        self.frappe.db.rollback.assert_called_once_with(save_point='conversation_event')

    def test_fresh_pin_check_is_required_for_protected_resume(self):
        self.conv.current_intent=None
        self.frappe.get_all.return_value=[self.task]
        self.frappe.get_doc.return_value=self.task
        secure=MagicMock(return_value={'allowed':False})
        modules={'ai_workplace.auth.gateway':SimpleNamespace(authorize=lambda *a,**k:{'allowed':True}),
                 'ai_workplace.security.authorization':SimpleNamespace(requires_pin=lambda _:True,authorize_whatsapp_service=secure)}
        with patch.dict('sys.modules',modules):
            _,out=backend.task_control(self.conv,self.context,'resume 1')
        self.assertIn('verify your PIN',out.body_text)
        self.assertIsNone(self.conv.current_intent)
        self.assertEqual(secure.call_args.args[1],'leave_apply')

    def test_metrics_never_store_drafts_or_user_message_text(self):
        self.frappe.db.exists.side_effect=lambda dt, value: dt=='DocType'
        doc=Doc()
        self.frappe.new_doc.return_value=doc
        backend.event(self.conv,'question','leave application','leave_apply')
        self.assertNotIn('private reason',json.dumps(doc))
        self.assertNotIn('draft_payload',doc)
        self.assertNotIn('employee',doc)


class TestLeavePrefill(unittest.TestCase):
    def setUp(self):
        self.conv=Doc(employee='E1',draft_payload=None)
        frappe=MagicMock()
        frappe._=lambda text:text
        def getdate(value=None):
            return date.fromisoformat(str(value)[:10]) if value else date(2026,11,2)
        def update(conv,**kwargs):
            for key,value in kwargs.items():
                conv['current_state' if key=='state' else key]=value
            return conv
        buttons=lambda text,**kwargs:OutboundMessage(body_text=text,interactive={'buttons':kwargs})
        fake={
            'frappe':frappe,
            'frappe.utils':SimpleNamespace(cint=lambda x:int(x or 0),formatdate=lambda value,fmt:str(value),getdate=getdate,today=lambda:'2026-11-02'),
            'ai_workplace.conversation.manager':SimpleNamespace(update_conversation=update),
            'ai_workplace.conversation.state':SimpleNamespace(ConversationState=SimpleNamespace(PROCESSING='PROCESSING',AWAITING_SELECTION='AWAITING_SELECTION')),
            'ai_workplace.services.attendance_leave':SimpleNamespace(get_leave_balance_data=lambda _: [{'leave_type':'Annual Leave'},{'leave_type':'Sick Leave'}]),
            'ai_workplace.services.response_helpers':SimpleNamespace(wrap_with_menu_again=lambda *a,**k:None,wrap_with_parent_menu=lambda text,*a,**k:OutboundMessage(body_text=text)),
            'ai_workplace.whatsapp.interactive':SimpleNamespace(build_leave_type_list_message=buttons,build_yes_no_buttons=buttons),
        }
        self.patch=patch.dict('sys.modules',fake)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        path=Path(__file__).parents[1]/'services'/'leave_apply.py'
        spec=importlib.util.spec_from_file_location('isolated_leave_prefill',path)
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module._build_leave_reason_list_message=lambda *a,**k:OutboundMessage(body_text='Select reason')

    def test_complete_sentence_reaches_confirmation_without_erp_write(self):
        create=MagicMock()
        self.module._create_leave_application=create
        out=self.module.start_leave_application(self.conv,{'employee':'E1'},'Apply for annual leave from 2026-11-10 to 2026-11-12 full days because family trip')
        draft=json.loads(self.conv.draft_payload)
        self.assertEqual(draft['step'],'awaiting_confirm')
        self.assertEqual(draft['description'],'family trip')
        self.assertIn('Submit',out.body_text)
        create.assert_not_called()

    def test_supplied_dates_are_reused_after_missing_reason_choice(self):
        self.module.start_leave_application(self.conv,{'employee':'E1'},'Apply for leave from 2026-11-10 to 2026-11-12 full days because family trip')
        self.assertEqual(json.loads(self.conv.draft_payload)['step'],'awaiting_leave_type')
        self.module.handle_leave_apply_message(self.conv,'Vacations',{'employee':'E1'})
        self.assertEqual(json.loads(self.conv.draft_payload)['step'],'awaiting_confirm')

    def test_from_date_reply_does_not_assume_end_date(self):
        self.module.start_leave_application(self.conv,{'employee':'E1'},'Apply for annual leave')
        self.module.handle_leave_apply_message(self.conv,'2026-11-10',{'employee':'E1'})
        draft=json.loads(self.conv.draft_payload)
        self.assertEqual(draft['step'],'awaiting_to_date')
        self.assertNotIn('to_date',draft)

    def test_missing_half_day_choice_is_asked_not_inferred(self):
        self.module.start_leave_application(self.conv,{'employee':'E1'},'Apply for annual leave from 2026-11-10 to 2026-11-12 because family trip')
        self.assertEqual(json.loads(self.conv.draft_payload)['step'],'awaiting_half_day')


class TestSelfServiceAPI(unittest.TestCase):
    def setUp(self):
        self.frappe=MagicMock()
        self.frappe.whitelist.side_effect=lambda *a,**k: lambda f:f
        self.frappe.session.user='person@example.com'
        self.patch=patch.dict('sys.modules',{'frappe':self.frappe})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        path=Path(__file__).parents[1]/'api'/'conversation_preferences.py'
        spec=importlib.util.spec_from_file_location('isolated_preferences',path)
        self.api=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def test_preferences_can_only_target_authenticated_user(self):
        with patch.object(backend,'save_preference',return_value={'reminders_enabled':0}) as save:
            self.api.update_preferences('0',20,9,'Asia/Karachi')
        self.assertEqual(save.call_args.args[0],'person@example.com')
        self.assertFalse(save.call_args.args[1])

    def test_guest_cannot_read_preferences(self):
        self.frappe.session.user='Guest'
        self.frappe.throw.side_effect=PermissionError
        with self.assertRaises(PermissionError):
            self.api.get_preferences()

    def test_invalid_boolean_does_not_silently_enable_reminders(self):
        self.frappe.throw.side_effect=ValueError
        with self.assertRaises(ValueError):
            self.api.update_preferences('false')

    def test_engagement_endpoint_requires_admin(self):
        path=Path(__file__).parents[1]/'api'/'conversation_engagement.py'
        spec=importlib.util.spec_from_file_location('isolated_engagement_api',path)
        api=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api)
        self.frappe.only_for.side_effect=PermissionError
        with self.assertRaises(PermissionError):
            api.get_engagement()


if __name__=='__main__':
    unittest.main()
