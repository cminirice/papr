import type { MultiplicationQuestion } from './api.generated'
export type ReadingQuestion = Omit<MultiplicationQuestion,'render_spec'|'answer'|'primary_knowledge_code'> & {
 render_spec:{kind:'number_read_write';number:number;reading:string}
 answer:{kind:'text';value:string}|{kind:'single_choice';value:string;correct_option_id:string}
}
export type Diagram={kind:string;[key:string]:unknown}
export type CurriculumQuestion=Omit<ReadingQuestion,'render_spec'|'question_type'> & {question_type:'choice'|'fill'|'answer'|'judgment'|'application';render_spec:{kind:'curriculum';component:string;index:number;seed:string;diagram:Diagram|null}}
export type PrintableQuestion=MultiplicationQuestion|ReadingQuestion|CurriculumQuestion
