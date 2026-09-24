from typing import List
from pydantic import BaseModel, Field, field_validator

class CharacterProfile(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    age:str=''
    gender:str=''
    appearance:str=''
    hair_style:str=''
    hair_colour:str=''
    skin_tone:str=''
    clothing:str=''
    accessories:str=''
    personality:str=''
    reference_image:str|None=None

    def prompt_description(self)->str:
        fields=(f'age {self.age}',f'gender {self.gender}',self.appearance,f'{self.hair_style} hair',f'{self.hair_colour} hair colour',f'{self.skin_tone} skin',f'wearing {self.clothing}',f'accessories: {self.accessories}',f'personality: {self.personality}')
        return f'{self.name}: '+', '.join(value for value in fields if value and not value.endswith(' '))
class ComicPanel(BaseModel):
    title:str=Field(min_length=1,max_length=100)
    scene:str=Field(min_length=1,max_length=1200)
    caption:str=Field(min_length=1,max_length=500)
    narration:str=Field(min_length=1,max_length=800)
    dialogue:str=Field(min_length=1,max_length=500)
    characters:List[str]=Field(default_factory=list)
    actions:str=''
    background:str=''
    camera_angle:str=''
    emotion:str=''
    image_prompt:str=''
    image_status:str='pending'
    image_error:str=''
class ComicStory(BaseModel):
    title:str=Field(min_length=1,max_length=160)
    character:str=Field(min_length=1,max_length=100)
    setting:str=Field(min_length=1,max_length=160)
    tone:str=Field(min_length=1,max_length=80)
    art_style:str=Field(min_length=1,max_length=160)
    colour_style:str='Full Color'
    theme:str=''
    characters:List[CharacterProfile]=Field(default_factory=list)
    panels:List[ComicPanel]=Field(min_length=1,max_length=9)
    @field_validator('panels')
    @classmethod
    def five(cls,v):
        if not 1 <= len(v) <= 9: raise ValueError('ComicCraft supports 1 to 9 panels.')
        return v
class GenerateRequest(BaseModel):
    story_title:str=''
    story_description:str=''
    genre:str='Adventure'
    panel_count:int=Field(default=5,ge=1,le=9)
    character:str='kanishka'
    setting:str='college library'
    custom_setting:str=''
    tone:str='Adventure'
    theme:str='Adventure'
    art_style:str='Modern comic book'
    custom_art_style:str=''
    colour_style:str='Full Color'
    custom_colour_style:str=''
    premise:str='A mysterious discovery begins an unexpected adventure.'
    characters:List[CharacterProfile]=Field(default_factory=list)

    @field_validator('panel_count')
    @classmethod
    def supported_panel_count(cls,value):
        if value < 1 or value > 9: raise ValueError('Panel count must be between 1 and 9.')
        return value
