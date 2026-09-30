#!/bin/sh
# usage: fin.sh <type> <dir-name> <html-name>
cd /Users/yajun/Documents/opensource/dsh-devlopment
D=.archify/dsh-guide-20260929-171932/$2
node ~/.claude/skills/archify/bin/archify.mjs finalize $1 $D/candidate.json $D/$3.html ${4:+--out-dir $D/$4} --repo-root deepseek-harness --quality showcase --json 2>&1 | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(j.status,JSON.stringify(j.gates));for(const d of j.diagnostics||[])console.log("-",d.code,d.message.slice(0,400));if(j.visualReviewRecommendation)console.log("hint",JSON.stringify(j.visualReviewRecommendation.hints||j.visualReviewRecommendation.signals));if(j.layoutReviewRecommendation)console.log("layout",JSON.stringify(j.layoutReviewRecommendation).slice(0,400))}catch(e){console.log(s.slice(-2000))}})'
