const operators={LTE:'≤',GTE:'≥',LT:'<',GT:'>',EQ:'=',NE:'≠',IN:'in',NOT_IN:'not in',EXISTS:'is present'};
export function relationshipLabel(value){return value.toLowerCase().replaceAll('_',' ')}
export function graphNodeLabel(node){
 const p=node.payload||node.properties;
 if(p&&node.type==='Threshold')return `${operators[p.operator]||p.operator} ${p.value}${p.unit==='%'?'%':p.unit?' '+p.unit:''}`;
 if(p&&node.type==='Condition')return `${p.field.replaceAll('_',' ')} ${operators[p.operator]||p.operator}${p.value!=null?' '+(Array.isArray(p.value)?p.value.join(', '):p.value):''}${p.unit?' '+p.unit:''}`;
 return node.label.replace(/\b(LTE|GTE|LT|GT|EQ|NE)\b/g,value=>operators[value]);
}
export function wrapGraphLabel(label,width=27){
 const words=label.split(/\s+/),lines=[];let line='';
 for(const word of words){if(line&&line.length+word.length+1>width){lines.push(line);line=word}else line+=(line?' ':'')+word}
 if(line)lines.push(line);
 return lines.length>3?[...lines.slice(0,2),lines[2].slice(0,width-1)+'…']:lines;
}
