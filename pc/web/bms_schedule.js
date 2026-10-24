'use strict';
// One browser-owned sequence: no overlap, no automatic restart after failure.
class BmsSnapshotSchedule {
  constructor({read,allowed=()=>true,onState=()=>{},schedule=(fn,delay)=>setTimeout(fn,delay),cancel=id=>clearTimeout(id)}){
    Object.assign(this,{read,allowed,onState,schedule,cancel});
    this.active=false;this.pending=false;this.timer=null;this.completed=0;this.message='尚未啟動定時快照';
  }
  emit(){this.onState({active:this.active,pending:this.pending,completed:this.completed,message:this.message});}
  start(interval){
    if(this.active||this.pending)throw new Error('請等本次讀取完成，再開始');
    if(![15000,30000,60000].includes(interval))throw new Error('請選擇 15、30 或 60 秒');
    if(!this.allowed())throw new Error('目前不能開始電池讀取');
    this.interval=interval;this.completed=0;this.active=true;this.message='定時快照已開始';this.emit();
    return this.tick();
  }
  stop(message='定時快照已停止'){
    this.active=false;if(this.timer!==null)this.cancel(this.timer);this.timer=null;
    this.message=message+(this.pending?'；本次已送出的讀取仍會完成並斷線':'');this.emit();
  }
  async tick(){
    this.timer=null;
    if(!this.active||this.pending)return;
    if(!this.allowed()){this.stop('目前狀態不允許讀取，排程已停止');return;}
    this.pending=true;this.message='正在讀取，完成後斷線';this.emit();
    try{await this.read();this.completed++;}
    catch(error){this.active=false;this.message='讀取或保存失敗，排程已停止；請確認後手動重試';}
    finally{this.pending=false;}
    if(this.active){
      this.message=`已完成 ${this.completed} 次；完成後間隔 ${this.interval/1000} 秒再讀取`;
      try{this.timer=this.schedule(()=>this.tick(),this.interval);}
      catch(error){this.active=false;this.message='計時器無法建立，排程已停止';}
    }else if(this.message.startsWith('定時快照已停止')){
      this.message='定時快照已停止；本次讀取已結束';
    }
    this.emit();
  }
}
if(typeof module!=='undefined')module.exports={BmsSnapshotSchedule};
