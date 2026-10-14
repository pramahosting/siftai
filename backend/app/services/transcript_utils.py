import re

def parse_vtt(content:str)->list[dict]:
    segments=[]
    for block in re.split(r"\n\s*\n",content.strip()):
        lines=[x.strip() for x in block.splitlines() if x.strip()]
        timing=next((x for x in lines if "-->" in x),None)
        if not timing: continue
        left,right=[x.strip().split()[0] for x in timing.split("-->",1)]
        def seconds(value):
            bits=value.replace(",",".").split(":"); return sum(float(v)*60**(len(bits)-i-1) for i,v in enumerate(bits))
        raw_text=" ".join(x for x in lines[lines.index(timing)+1:] if not x.startswith("WEBVTT"))
        speaker_match=re.search(r"<v\s+([^>]+)>",raw_text)
        speaker=speaker_match.group(1).strip() if speaker_match else None
        text=re.sub(r"<[^>]+>","",raw_text)
        if text: segments.append({"start":seconds(left),"end":seconds(right),"speaker":speaker,"text":text})
    return segments
