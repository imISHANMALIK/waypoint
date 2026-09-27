import { useEffect, useRef } from 'react';
import Phaser from 'phaser';
import type { World, Point } from './types';

const project = (x:number,y:number,z=0) => ({x:395+(x-y)*21,y:32+(x+y)*11-z});
const colors=[0xc4e69d,0x8dd1e2,0xe7c588,0xa7b6ee,0xe6b0bf,0x96d5ba];

class Floor extends Phaser.Scene {
  world!:World;
  routes=true;
  selected='AMR-01';
  select:(id:string)=>void=()=>{};
  robots=new Map<string,Phaser.GameObjects.Container>();
  paths!:Phaser.GameObjects.Graphics;
  closure!:Phaser.GameObjects.Graphics;
  ready=false;
  constructor(){super('Warehouse');}
  diamond(g:Phaser.GameObjects.Graphics,x:number,y:number,color:number,alpha=1,z=0){
    const p=[project(x-.46,y-.46,z),project(x+.46,y-.46,z),project(x+.46,y+.46,z),project(x-.46,y+.46,z)];
    g.fillStyle(color,alpha);g.fillPoints(p,true);
  }
  create(){
    const g=this.add.graphics();
    for(let x=0;x<25;x++)for(let y=0;y<17;y++){
      this.diamond(g,x,y,(x===0||y===0||x===24||y===16)?0x344641:((x+y)%2?0x263a35:0x283c37));
    }
    this.paths=this.add.graphics().setDepth(1);
    this.closure=this.add.graphics().setDepth(2);
    const racks=this.world.layout.racks;
    // Raised cells directly encode occupied rack locations in the simulation grid.
    for(const [x,y] of racks){
      const rack=this.add.graphics().setDepth(x+y+5);
      const a=project(x-.43,y-.43,22),b=project(x+.43,y-.43,22),c=project(x+.43,y+.43,22),d=project(x-.43,y+.43,22);
      rack.fillStyle(0x527166);rack.fillPoints([d,c,project(x+.43,y+.43),project(x-.43,y+.43)],true);
      rack.fillStyle(0x3b584c);rack.fillPoints([b,c,project(x+.43,y+.43),project(x+.43,y-.43)],true);
      rack.fillStyle(0x8ba592);rack.fillPoints([a,b,c,d],true);
      rack.lineStyle(.7,0xa9c0aa,.35);rack.strokePoints([a,b,c,d],true);
      const p=project(x,y,24);rack.fillStyle(0xb6cbb1,.65);rack.fillRoundedRect(p.x-5,p.y-3,10,5,1);
    }
    ['A','B','C','D'].forEach((s,i)=>{const p=project([4,8,14,18][i],1);this.add.text(p.x,p.y-15,`ZONE ${s}`,{fontFamily:'monospace',fontSize:'10px',color:'#b6c9ba'}).setOrigin(.5);});
    for(const [i,dock] of this.world.layout.docks.entries()){
      this.diamond(g,dock[0],dock[1],0xb8d49b,.55);
      const p=project(dock[0]+1.5,dock[1]);this.add.text(p.x+10,p.y,`D0${i+1}`,{fontFamily:'monospace',fontSize:'10px',color:'#bdd4c3'}).setOrigin(0,.5);
    }
    const entry=project(1,12);this.add.text(entry.x-32,entry.y,'RECEIVING',{fontFamily:'monospace',fontSize:'9px',color:'#849e90'}).setAngle(28);
    const out=project(23,8);this.add.text(out.x+18,out.y+15,'DISPATCH →',{fontFamily:'monospace',fontSize:'9px',color:'#aec1b2'}).setAngle(-28);
    this.ready=true;this.paint(false);
  }
  paint(animate=true){
    if(!this.ready)return;
    this.paths.clear();this.closure.clear();
    for(const [x,y] of this.world.blocked){this.diamond(this.closure,x,y,0xe5ad72,.65);const p=project(x,y);this.closure.lineStyle(1,0xffd29b,.8);this.closure.lineBetween(p.x-6,p.y-3,p.x+6,p.y+3);}
    for(const [index,robot] of this.world.robots.entries()){
      const color=colors[index%colors.length];
      if(this.routes && robot.path.length){const points=[robot.pos,...robot.path].map(p=>project(...p,2));this.paths.lineStyle(robot.id===this.selected?2:1.2,color,robot.id===this.selected?.7:.22);this.paths.strokePoints(points,false);}
      let container=this.robots.get(robot.id);
      if(!container){
        const shadow=this.add.ellipse(0,3,27,13,0x101f18,.7);
        const ring=this.add.ellipse(0,0,32,17).setStrokeStyle(1.5,color,.8).setName('ring');
        const body=this.add.graphics();body.fillStyle(0x172a25);body.fillRoundedRect(-11,-12,22,15,5);body.fillStyle(color);body.fillRoundedRect(-10,-16,20,14,4);body.fillStyle(0x223d32);body.fillRoundedRect(-5,-13,10,6,2);body.fillStyle(0xf1ffdf);body.fillCircle(7,-8,1.7);
        const label=this.add.text(0,-30,robot.id.replace('AMR-','R'),{fontFamily:'monospace',fontSize:'10px',color:'#e0edd8',backgroundColor:'#20332c',padding:{x:4,y:2}}).setOrigin(.5);
        container=this.add.container(0,0,[shadow,ring,body,label]);
        container.setSize(38,42).setInteractive({useHandCursor:true}).on('pointerdown',()=>this.select(robot.id));
        this.robots.set(robot.id,container);
      }
      container.getByName('ring').setActive(robot.id===this.selected);
      (container.getByName('ring') as Phaser.GameObjects.Ellipse).setVisible(robot.id===this.selected);
      const p=project(...robot.pos,3);container.setDepth(robot.pos[0]+robot.pos[1]+6);
      this.tweens.killTweensOf(container);
      if(animate)this.tweens.add({targets:container,x:p.x,y:p.y,duration:420,ease:'Linear'});else container.setPosition(p.x,p.y);
    }
  }
}

export default function Warehouse({world,selected,onSelect,routes,zoom}:{world:World;selected:string;onSelect:(id:string)=>void;routes:boolean;zoom:number}){
  const host=useRef<HTMLDivElement>(null);const scene=useRef<Floor|null>(null);const onSelectRef=useRef(onSelect);onSelectRef.current=onSelect;
  useEffect(()=>{if(!host.current)return;const floor=new Floor();floor.world=world;floor.select=id=>onSelectRef.current(id);scene.current=floor;const game=new Phaser.Game({type:Phaser.AUTO,width:900,height:520,parent:host.current,backgroundColor:'#20332e',scene:floor,antialias:true,scale:{mode:Phaser.Scale.FIT,autoCenter:Phaser.Scale.CENTER_BOTH},audio:{noAudio:true}});return()=>{scene.current=null;game.destroy(true);};},[]);
  useEffect(()=>{if(scene.current){scene.current.world=world;scene.current.selected=selected;scene.current.routes=routes;scene.current.paint();if(scene.current.ready)scene.current.cameras.main.setZoom(zoom);}},[world,selected,routes,zoom]);
  return <div ref={host} className="warehouse-canvas" role="img" aria-label={`Isometric warehouse with ${world.metrics.active_robots} active robots. ${world.incident?'Central aisle closed.':''} Use the fleet buttons below to select a robot.`}/>;
}
