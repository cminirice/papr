<script setup lang="ts">
import {computed} from 'vue'
import type {Diagram} from './printable'
const props=defineProps<{diagram:Diagram}>()
const n=(key:string)=>Number(props.diagram[key]??0)
const cell=computed(()=>Math.min(260/Math.max(1,n('cols')),120/Math.max(1,n('rows'))))
const count=computed(()=>Math.min(n('n'),12))
const anglePoint=computed(()=>({x:30+110*Math.cos(n('angle')*Math.PI/180),y:130-110*Math.sin(n('angle')*Math.PI/180)}))
const bars=computed(()=>props.diagram.kind==='bars'?(props.diagram.values as number[]):[])
const labels=computed(()=>props.diagram.kind==='bars'?(props.diagram.labels as string[]):[])
</script>
<template>
 <figure class="curriculum-diagram">
 <svg v-if="diagram.kind==='angle'" viewBox="-90 0 300 160" role="img" :aria-label="n('angle')+'度角示意图'"><path d="M 150 130 L 30 130"/><line x1="30" y1="130" :x2="anglePoint.x" :y2="anglePoint.y"/><text x="40" y="115">{{n('angle')}}°</text></svg>
 <svg v-else-if="diagram.kind==='bars'" viewBox="0 0 300 180" role="img" aria-label="带数值标注的条形统计图"><path d="M 25 15 V 145 H 290"/><g v-for="(v,i) in bars" :key="i"><rect :x="40+i*62" :y="140-v/Math.max(...bars)*100" width="30" :height="v/Math.max(...bars)*100"/><text :x="55+i*62" :y="132-v/Math.max(...bars)*100" text-anchor="middle">{{v}}</text><text :x="55+i*62" y="163" text-anchor="middle">{{labels[i]}}</text></g><text x="5" y="12">{{diagram.unit}}</text></svg>
 <svg v-else-if="diagram.kind==='rect_grid'" viewBox="0 0 300 160" role="img" aria-label="完整方格图"><line v-for="i in n('cols')+1" :key="'c'+i" :x1="20+(i-1)*cell" y1="15" :x2="20+(i-1)*cell" :y2="15+n('rows')*cell"/><line v-for="i in n('rows')+1" :key="'r'+i" x1="20" :y1="15+(i-1)*cell" :x2="20+n('cols')*cell" :y2="15+(i-1)*cell"/></svg>
 <svg v-else-if="diagram.kind==='segments'||diagram.kind==='fan'" viewBox="0 0 300 160" role="img" aria-label="点与连线示意图"><line x1="20" y1="130" x2="280" y2="130"/><g v-for="i in count" :key="i"><circle :cx="20+(i-1)*260/(count-1)" cy="130" r="3"/><line v-if="diagram.kind==='fan'" x1="150" y1="25" :x2="20+(i-1)*260/(count-1)" y2="130"/></g><text v-if="diagram.kind==='fan'" x="145" y="18">P</text></svg>
 <svg v-else-if="diagram.kind==='rectangle'" viewBox="0 0 300 160" role="img" aria-label="长方形尺寸示意图"><rect x="50" y="30" width="210" height="100"/><text x="155" y="20" text-anchor="middle">{{diagram.a}}米</text><text x="0" y="85">{{diagram.b}}米</text></svg>
 <svg v-else-if="diagram.kind==='squares'" viewBox="0 0 300 100" role="img" aria-label="横向拼摆正方形示意图"><rect v-for="i in Math.min(n('n'),8)" :key="i" :x="10+(i-1)*34" y="20" width="34" height="34"/></svg>
 <svg v-else-if="diagram.kind==='grid'" viewBox="0 0 300 150" role="img" aria-label="向右再向上的路线示意图"><path d="M 25 120 H 240 V 25"/><text x="12" y="140">A</text><text x="235" y="18">B</text><text x="115" y="140">向右 {{diagram.dx}}格</text><text x="135" y="65">向上 {{diagram.dy}}格</text><text x="5" y="20">上北下南，左西右东</text></svg>
 <figcaption v-if="['segments','fan'].includes(diagram.kind)&&n('n')>12">示意图仅展示部分点；按题干给出的{{diagram.n}}个点计数。</figcaption>
 <figcaption v-else-if="diagram.kind==='squares'&&n('n')>8">图中只展示前8个正方形，整排共{{diagram.n}}个。</figcaption>
 <figcaption v-else-if="['angle','rectangle','grid'].includes(diagram.kind)">示意图不按实际比例绘制，以题干数据为准。</figcaption>
 </figure>
</template>
<style scoped>
.curriculum-diagram{margin:3mm 0;break-inside:avoid}.curriculum-diagram svg{display:block;width:100%;max-width:75mm;max-height:45mm}.curriculum-diagram path,.curriculum-diagram line,.curriculum-diagram rect{fill:none;stroke:#111;stroke-width:1.3}.curriculum-diagram rect{fill:#eee}.curriculum-diagram circle{fill:#111}.curriculum-diagram text{font-size:12px;fill:#111}.curriculum-diagram figcaption{font-size:8pt}
</style>
