const test=require('node:test');
const assert=require('node:assert/strict');
const {BmsSnapshotSchedule}=require('./web/bms_schedule.js');
function setup(read){
  const timers=[];const cancelled=[];
  const s=new BmsSnapshotSchedule({read,schedule:(fn,delay)=>{timers.push({fn,delay});return timers.length;},cancel:id=>cancelled.push(id)});
  return {s,timers,cancelled};
}
test('waits for completion before scheduling and cancels next read',async()=>{
  let complete;let calls=0;
  const {s,timers,cancelled}=setup(()=>{calls++;return new Promise(r=>complete=r);});
  const pending=s.start(15000);assert.equal(calls,1);assert.equal(timers.length,0);
  assert.throws(()=>s.start(15000));complete();await pending;
  assert.equal(timers.length,1);assert.equal(timers[0].delay,15000);
  s.stop();assert.deepEqual(cancelled,[1]);await timers[0].fn();assert.equal(calls,1);
});
test('stopping in-flight permits completion but never schedules another read',async()=>{
  let complete;const {s,timers}=setup(()=>new Promise(r=>complete=r));
  const pending=s.start(30000);s.stop();assert.equal(s.pending,true);
  assert.throws(()=>s.start(30000));complete();await pending;
  assert.equal(timers.length,0);assert.equal(s.completed,1);assert.equal(s.active,false);
});
test('failed read stops without reconnect loop',async()=>{
  const {s,timers}=setup(async()=>{throw new Error('offline');});
  await s.start(60000);assert.equal(s.active,false);assert.equal(s.pending,false);assert.equal(timers.length,0);
});
test('next read checks changed permissions and invalid intervals are rejected',async()=>{
  let allowed=true,calls=0;const {s,timers}=setup(async()=>calls++);s.allowed=()=>allowed;
  assert.throws(()=>s.start(0));await s.start(15000);allowed=false;
  await timers[0].fn();assert.equal(calls,1);assert.equal(s.active,false);
});
test('timer creation failure leaves no active schedule',async()=>{
  const {s}=setup(async()=>{});s.schedule=()=>{throw new Error('timer failed');};
  await s.start(15000);assert.equal(s.active,false);assert.equal(s.pending,false);assert.equal(s.timer,null);
});
