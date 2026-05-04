document.addEventListener('DOMContentLoaded', function() {

// SNAKE II — Nokia 7110 style
// ══════════════════════════════════════════
(function(){
  const CELL=14, COLS=20, ROWS=20;
  const canvas=document.getElementById('snake-canvas');
  const ctx=canvas.getContext('2d');
  const overlay=document.getElementById('snake-overlay');
  const scoreEl=document.getElementById('snake-score');
  const hiEl=document.getElementById('snake-hi');
  const startBtn=document.getElementById('snake-start');

  // Nokia palette
  const BG='#8a9a5b', DARK='#2b3a0e', LIGHT='#c8d87a';

  let snake, dir, nextDir, food, score, hiScore=0, running=false, loop;

  function init(){
    snake=[{x:10,y:10},{x:9,y:10},{x:8,y:10}];
    dir={x:1,y:0}; nextDir={x:1,y:0};
    score=0; placeFood(); draw();
  }

  function placeFood(){
    let pos;
    do { pos={x:Math.floor(Math.random()*COLS),y:Math.floor(Math.random()*ROWS)}; }
    while(snake.some(s=>s.x===pos.x&&s.y===pos.y));
    food=pos;
  }

  function step(){
    dir=nextDir;
    const head={x:(snake[0].x+dir.x+COLS)%COLS, y:(snake[0].y+dir.y+ROWS)%ROWS};
    if(snake.some(s=>s.x===head.x&&s.y===head.y)){ gameOver(); return; }
    snake.unshift(head);
    if(head.x===food.x&&head.y===food.y){
      score+=10; scoreEl.textContent=String(score).padStart(3,'0');
      if(score>hiScore){hiScore=score;hiEl.textContent='HI: '+String(hiScore).padStart(3,'0');}
      placeFood();
    } else { snake.pop(); }
    draw();
  }

  function draw(){
    ctx.fillStyle=BG; ctx.fillRect(0,0,canvas.width,canvas.height);
    // Grid dots
    ctx.fillStyle='rgba(0,0,0,.15)';
    for(let x=0;x<COLS;x++) for(let y=0;y<ROWS;y++){
      ctx.fillRect(x*CELL+CELL/2-1,y*CELL+CELL/2-1,2,2);
    }
    // Food — blinking square
    ctx.fillStyle=DARK;
    ctx.fillRect(food.x*CELL+2,food.y*CELL+2,CELL-4,CELL-4);
    ctx.fillStyle=LIGHT;
    ctx.fillRect(food.x*CELL+4,food.y*CELL+4,CELL-8,CELL-8);
    // Snake
    snake.forEach((s,i)=>{
      ctx.fillStyle=i===0?DARK:'#3d5219';
      ctx.fillRect(s.x*CELL+1,s.y*CELL+1,CELL-2,CELL-2);
      if(i===0){
        // Eyes
        ctx.fillStyle=LIGHT;
        const ex=s.x*CELL+CELL/2, ey=s.y*CELL+CELL/2;
        const ox=dir.y*3, oy=dir.x*3;
        ctx.fillRect(ex+dir.x*2-1+ox, ey+dir.y*2-1+oy, 2, 2);
        ctx.fillRect(ex+dir.x*2-1-ox, ey+dir.y*2-1-oy, 2, 2);
      }
    });
  }

  function gameOver(){
    clearInterval(loop); running=false;
    overlay.querySelector('.juego-overlay-title').textContent='FIN';
    overlay.querySelector('.juego-overlay-sub').textContent='Puntuación: '+score;
    startBtn.textContent='▶ Reiniciar';
    overlay.style.display='flex';
  }

  startBtn.addEventListener('click',()=>{
    overlay.style.display='none';
    init();
    if(loop)clearInterval(loop);
    running=true;
    let speed=150;
    loop=setInterval(()=>{
      step();
      // Speed up every 50 points
      const newSpeed=Math.max(60,150-Math.floor(score/50)*10);
      if(newSpeed!==speed){ clearInterval(loop); speed=newSpeed; loop=setInterval(step,speed); }
    },speed);
    startBtn.textContent='▶ Reiniciar';
  });

  const DIRS={ArrowUp:{x:0,y:-1},ArrowDown:{x:0,y:1},ArrowLeft:{x:-1,y:0},ArrowRight:{x:1,y:0},
              w:{x:0,y:-1},s:{x:0,y:1},a:{x:-1,y:0},d:{x:1,y:0},
              W:{x:0,y:-1},S:{x:0,y:1},A:{x:-1,y:0},D:{x:1,y:0}};
  document.addEventListener('keydown',e=>{
    if(!running)return;
    const d=DIRS[e.key];
    if(d&&!(d.x===-dir.x&&d.y===-dir.y)){
      nextDir=d;
      if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key))e.preventDefault();
    }
  });

  // Swipe support
  let tx=0,ty=0;
  canvas.addEventListener('touchstart',e=>{tx=e.touches[0].clientX;ty=e.touches[0].clientY},{passive:true});
  canvas.addEventListener('touchend',e=>{
    if(!running)return;
    const dx=e.changedTouches[0].clientX-tx, dy=e.changedTouches[0].clientY-ty;
    if(Math.abs(dx)>Math.abs(dy)){nextDir=dx>0?{x:1,y:0}:{x:-1,y:0};}
    else{nextDir=dy>0?{x:0,y:1}:{x:0,y:-1};}
  },{passive:true});

  init();
})();

// ══════════════════════════════════════════
// TETRIS
// ══════════════════════════════════════════
(function(){
  const COLS=10,ROWS=20,SZ=20;
  const canvas=document.getElementById('tetris-canvas');
  const ctx=canvas.getContext('2d');
  const nextCanvas=document.getElementById('tetris-next');
  const nextCtx=nextCanvas.getContext('2d');
  const overlay=document.getElementById('tetris-overlay');
  const scoreEl=document.getElementById('tetris-score');
  const hiEl=document.getElementById('tetris-hi');
  const startBtn=document.getElementById('tetris-start');

  const PIECES=[
    {shape:[[1,1,1,1]],color:'#00f0f0'},             // I
    {shape:[[1,1],[1,1]],color:'#f0f000'},            // O
    {shape:[[0,1,0],[1,1,1]],color:'#a000f0'},        // T
    {shape:[[0,1,1],[1,1,0]],color:'#00f000'},        // S
    {shape:[[1,1,0],[0,1,1]],color:'#f00000'},        // Z
    {shape:[[1,0,0],[1,1,1]],color:'#0000f0'},        // J
    {shape:[[0,0,1],[1,1,1]],color:'#f0a000'},        // L
  ];

  let board,piece,next,score,lines,level,hiScore=0,running=false,loop,dropTimer,dropInterval;

  function newBoard(){ return Array.from({length:ROWS},()=>Array(COLS).fill(0)); }

  function randPiece(){
    const p=PIECES[Math.floor(Math.random()*PIECES.length)];
    return{shape:p.shape.map(r=>[...r]),color:p.color,
           x:Math.floor(COLS/2)-Math.floor(p.shape[0].length/2),y:0};
  }

  function rotate(shape){
    return shape[0].map((_,i)=>shape.map(r=>r[i]).reverse());
  }

  function valid(s,x,y){
    return s.every((row,dy)=>row.every((v,dx)=>{
      if(!v)return true;
      const nx=x+dx,ny=y+dy;
      return nx>=0&&nx<COLS&&ny<ROWS&&(ny<0||!board[ny][nx]);
    }));
  }

  function lock(){
    piece.shape.forEach((row,dy)=>row.forEach((v,dx)=>{
      if(v&&piece.y+dy>=0) board[piece.y+dy][piece.x+dx]=piece.color;
    }));
    // Clear lines
    let cleared=0;
    for(let y=ROWS-1;y>=0;y--){
      if(board[y].every(c=>c)){
        board.splice(y,1);board.unshift(Array(COLS).fill(0));
        cleared++;y++;
      }
    }
    if(cleared){
      const pts=[0,100,300,500,800][cleared]*level;
      score+=pts; lines+=cleared;
      level=Math.floor(lines/10)+1;
      dropInterval=Math.max(50,500-level*40);
      scoreEl.textContent=String(score).padStart(6,'0');
      hiEl.textContent='NIVEL: '+level+' · LÍNEAS: '+lines;
      if(score>hiScore)hiScore=score;
    }
    piece=next; next=randPiece();
    if(!valid(piece.shape,piece.x,piece.y)){gameOver();return;}
    drawNext();
  }

  function drop(){
    if(valid(piece.shape,piece.x,piece.y+1)){piece.y++;}
    else{lock();}
    draw();
  }

  function draw(){
    ctx.fillStyle='#111'; ctx.fillRect(0,0,canvas.width,canvas.height);
    // Grid
    ctx.strokeStyle='rgba(255,255,255,.04)';ctx.lineWidth=.5;
    for(let x=0;x<=COLS;x++){ctx.beginPath();ctx.moveTo(x*SZ,0);ctx.lineTo(x*SZ,ROWS*SZ);ctx.stroke();}
    for(let y=0;y<=ROWS;y++){ctx.beginPath();ctx.moveTo(0,y*SZ);ctx.lineTo(COLS*SZ,y*SZ);ctx.stroke();}
    // Board
    board.forEach((row,y)=>row.forEach((color,x)=>{
      if(color){drawCell(ctx,x,y,color);}
    }));
    // Ghost piece
    let gy=piece.y;
    while(valid(piece.shape,piece.x,gy+1))gy++;
    piece.shape.forEach((row,dy)=>row.forEach((v,dx)=>{
      if(v&&gy+dy>=0){
        ctx.fillStyle='rgba(255,255,255,.1)';
        ctx.fillRect((piece.x+dx)*SZ+1,(gy+dy)*SZ+1,SZ-2,SZ-2);
      }
    }));
    // Active piece
    piece.shape.forEach((row,dy)=>row.forEach((v,dx)=>{
      if(v&&piece.y+dy>=0)drawCell(ctx,piece.x+dx,piece.y+dy,piece.color);
    }));
  }

  function drawCell(c,x,y,color){
    c.fillStyle=color;
    c.fillRect(x*SZ+1,y*SZ+1,SZ-2,SZ-2);
    c.fillStyle='rgba(255,255,255,.25)';
    c.fillRect(x*SZ+1,y*SZ+1,SZ-2,3);
    c.fillRect(x*SZ+1,y*SZ+1,3,SZ-2);
    c.fillStyle='rgba(0,0,0,.2)';
    c.fillRect(x*SZ+1,y*SZ+SZ-4,SZ-2,3);
  }

  function drawNext(){
    nextCtx.fillStyle='#111';nextCtx.fillRect(0,0,80,80);
    const ns=next.shape, ox=Math.floor((4-ns[0].length)/2), oy=Math.floor((4-ns.length)/2);
    ns.forEach((row,dy)=>row.forEach((v,dx)=>{
      if(v){
        nextCtx.fillStyle=next.color;
        nextCtx.fillRect((ox+dx)*18+4,(oy+dy)*18+4,16,16);
        nextCtx.fillStyle='rgba(255,255,255,.25)';
        nextCtx.fillRect((ox+dx)*18+4,(oy+dy)*18+4,16,3);
      }
    }));
  }

  function gameOver(){
    clearInterval(loop);running=false;
    overlay.querySelector('.juego-overlay-title').textContent='GAME OVER';
    overlay.querySelector('.juego-overlay-sub').textContent='Líneas: '+lines;
    document.getElementById('tetris-lines-final').textContent=lines;
    startBtn.textContent='▶ Reiniciar';
    overlay.style.display='flex';
  }

  function startGame(){
    board=newBoard();score=0;lines=0;level=1;dropInterval=460;
    scoreEl.textContent='000000';hiEl.textContent='NIVEL: 1 · LÍNEAS: 0';
    piece=randPiece();next=randPiece();
    overlay.style.display='none';running=true;
    if(loop)clearInterval(loop);
    dropTimer=0;
    let last=0;
    function tick(ts){
      if(!running)return;
      if(!last)last=ts;
      dropTimer+=ts-last;last=ts;
      if(dropTimer>=dropInterval){drop();dropTimer=0;}
      draw();
      loop=requestAnimationFrame(tick);
    }
    loop=requestAnimationFrame(tick);
    drawNext();
  }

  startBtn.addEventListener('click',startGame);

  document.addEventListener('keydown',e=>{
    if(!running)return;
    if(e.key==='ArrowLeft'&&valid(piece.shape,piece.x-1,piece.y)){piece.x--;draw();}
    else if(e.key==='ArrowRight'&&valid(piece.shape,piece.x+1,piece.y)){piece.x++;draw();}
    else if(e.key==='ArrowDown'){drop();dropTimer=0;}
    else if(e.key==='ArrowUp'){
      const r=rotate(piece.shape);
      if(valid(r,piece.x,piece.y)){piece.shape=r;draw();}
      else if(valid(r,piece.x-1,piece.y)){piece.x--;piece.shape=r;draw();}
      else if(valid(r,piece.x+1,piece.y)){piece.x++;piece.shape=r;draw();}
    }
    else if(e.key===' '){
      while(valid(piece.shape,piece.x,piece.y+1))piece.y++;
      drop();dropTimer=0;
      e.preventDefault();
    }
    if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' '].includes(e.key))e.preventDefault();
  });

  // Draw initial screens
  ctx.fillStyle='#111';ctx.fillRect(0,0,canvas.width,canvas.height);
  nextCtx.fillStyle='#111';nextCtx.fillRect(0,0,80,80);
})();


});