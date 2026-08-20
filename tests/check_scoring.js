const BOARD_MODEL={3:{target:35,floor:180,errorAllowance:1,scoreMean:.7,scoreSpread:.2},4:{target:90,floor:360,errorAllowance:1.25,scoreMean:.62,scoreSpread:.2},5:{target:170,floor:520,errorAllowance:1.5,scoreMean:.52,scoreSpread:.24}};

function speedScoreFactor(seconds,target){
  const ratio=Math.min(1,target/Math.max(1,seconds));
  return Math.max(0,Math.min(1,ratio-.6*ratio*(1-ratio)*(ratio-.5)));
}

function score(boardSize,pairCount,wrongAttempts,seconds){
  const model=BOARD_MODEL[boardSize];
  const density=wrongAttempts/Math.max(1,pairCount);
  const accuracy=Math.exp(-density/(.65*model.errorAllowance));
  const speed=speedScoreFactor(seconds,model.target);
  const performance=accuracy*.9+speed*.1;
  const standardized=(performance-model.scoreMean)/model.scoreSpread;
  const excellenceBonus=performance>.9?80*((performance-.9)/.1)**2:0;
  if(wrongAttempts===0&&seconds<=model.target)return 1000;
  return Math.max(model.floor,Math.min(1000,Math.round(750+standardized*100+excellenceBonus)));
}

function assert(condition,message){if(!condition)throw new Error(message)}

assert(score(3,4,0,35)===1000,"3×3正常无错应可得1000分");
assert(score(4,8,0,90)===1000,"4×4正常无错应可得1000分");
assert(score(5,12,0,170)===1000,"5×5正常无错应可得1000分");
assert(score(4,8,2,100)>=800,"4×4少量错误应保持积极反馈");
assert(score(5,12,6,200)>=780,"5×5中等错误应保持积极反馈");
assert(score(5,12,12,340)>=680,"5×5完成但错误较多时不应出现挫败性超低分");
assert(score(4,8,2,100)<900&&score(5,12,6,200)<900,"常见表现应集中在中间分段");
assert(score(5,12,6,180)>score(3,4,2,42),"相同错误密度下5×5应体现更高记忆负荷");
assert(score(5,12,1,150)<1000,"存在有效错误时不能获得满分");

console.log("分规模评分模型边界正常",{
  easyPerfect:score(3,4,0,35),
  standardTwoErrors:score(4,8,2,100),
  largeSixErrors:score(5,12,6,200),
  largeHeavyErrors:score(5,12,12,340),
});
