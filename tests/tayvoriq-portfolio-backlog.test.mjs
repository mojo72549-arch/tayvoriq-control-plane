import test from 'node:test';
import assert from 'node:assert/strict';
import {topicsOf,progress} from '../tools/portfolio-batch/advance.mjs';
test('separate topics are kept in order; duplicate topics, blanks and excessive batches are guarded',()=>{
 assert.deepEqual(topicsOf([' Stuttgart Bahn ','STUTTGART BAHN','USB-C']),['Stuttgart Bahn','USB-C']);
 for(const list of [[],['a'],Array(11).fill('abc'),['abc\ndef']])assert.throws(()=>topicsOf(list));
});
test('a failed research item is closed; delivered, undecided topics remain actionable',()=>{
 const row={selection_id:'s',day:'2026-11-28'};
 assert.equal(progress(row,{run:{status:'completed',conclusion:'failure'}}).state,'NO_SELECTION');
 const delivery={telegram_delivery_verified:true,selection_id:'s'};
 assert.equal(progress(row,{delivery,today:row.day}).state,'AWAITING_TOPIC');
 assert.equal(progress(row,{delivery,today:'2026-11-29'}).state,'EXPIRED');
});
test('completion requires a matching delivery, actual master review, and Telegram receipt',()=>{
 const request={request_id:'x',golden_path_run_id:11,source_context_sha256:'abc',production_completion:{
   state:'REVIEW_READY',quality_gates_weakened:false,golden_path_run_id:11,telegram_message_id:100}};
 const decision={request_id:'x',review_id:'11',telegram_message_id:100,source_context_sha256:'abc'};
 assert.equal(progress({},{request,decision}).state,'REVIEW_READY');
 assert.equal(progress({},{request,decision:{...decision,telegram_message_id:6}}).state,'PRODUCING');
});
