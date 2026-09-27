export type Point = [number, number];
export interface Order {id:string;shelf:string;priority:string;due_tick:number;units:number;status:string;robot:string|null;started_tick:number|null;completed_tick:number|null}
export interface Robot {id:string;pos:Point;path:Point[];order:string|null;phase:string;distance:number}
export interface Metrics {total:number;completed:number;queued:number;in_progress:number;at_risk:number;on_time:number|null;throughput:number;average_cycle:number|null;distance:number;active_robots:number}
export interface World {id:string;revision:number;tick:number;policy:string;incident:boolean;blocked:Point[];orders:Order[];robots:Robot[];metrics:Metrics;events:{tick:number;kind:string;text:string}[];history:(Metrics & {tick:number})[];layout:{width:number;height:number;racks:Point[];shelves:Record<string,Point>;docks:Point[]}}
export interface Comparison extends Metrics {policy:string;newly_completed:number;additional_distance:number}
export interface Plan {id:string;objective:string;status:string;created_at:string;based_on_tick:number;workspace_id:string;revision:number;recommendation:string;summary:string;mode:string;comparisons:Comparison[];trace:{step:string;detail:string}[]}
export const policyNames:Record<string,string> = {fifo:'First in, first out',nearest:'Nearest pick',priority:'Urgent first'};
export function simTime(tick:number) {const seconds=tick*10;return `${String(Math.floor(seconds/3600)).padStart(2,'0')}:${String(Math.floor(seconds/60)%60).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;}
export class ApiError extends Error {constructor(message:string,public status:number){super(message);}}
export async function api<T>(path:string,body?:unknown):Promise<T> {const response=await fetch(`/api${path}`,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!response.ok){const error=await response.json().catch(()=>({detail:'Request failed'}));throw new ApiError(typeof error.detail==='string'?error.detail:'Please check the input and try again.',response.status);}return response.json();}
