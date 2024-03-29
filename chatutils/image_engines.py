# Description: Image Generation Engines for SirChatalot

import configparser
config = configparser.ConfigParser()
config.read('./data/.config')
LogLevel = config.get("Logging", "LogLevel") if config.has_option("Logging", "LogLevel") else "WARNING"

# logging
import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger("SirChatalot-ImageEngines")
LogLevel = getattr(logging, LogLevel.upper())
logger.setLevel(LogLevel)
handler = TimedRotatingFileHandler('./logs/sirchatalot.log',
                                       when="D",
                                       interval=1,
                                       backupCount=7)
handler.setFormatter(logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s',"%Y-%m-%d %H:%M:%S"))
logger.addHandler(handler)

import os
import hashlib
import asyncio
import json
import time


######## OpenAI Engine ########

class DalleEngine:
    def __init__(self, api_key, base_url=None):
        '''
        Initialize OpenAI API for DALL-E
        '''
        from openai import AsyncOpenAI
        import openai 
        self.openai = openai
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        import configparser
        self.config = configparser.SafeConfigParser({
            "ImageGenModel": "dall-e-3",
            "ImageGenerationSize": "1024x1024",
            "ImageGenerationStyle": "vivid",
            "ImageGenerationQuality": "standard",
            "ImageGenerationPrice": 0,
            "ImageRateLimitCount": 0,
            "ImageRateLimitTime": 0,
        })
        self.config.read('./data/.config')

        if "ImageGeneration" in self.config.sections():
            self.settings = self.load_image_generation_settings()
        else:
            self.settings = self.load_image_generation_settings(deprecated=True)
        if self.settings is None:
            raise Exception('Could not load image generation settings')

        print('Image generation via DALL-E is enabled')
        print('-- Image generation is used to create images from text. It can be changed in the config file.')
        if self.settings["ImageRateLimitCount"] > 0 and self.settings["ImageRateLimitTime"] > 0:
            self.image_rate_limit = {}
            print(f'-- Image generation is rate limited (only {self.settings["ImageRateLimitCount"]} images per {self.settings["ImageRateLimitTime"]} seconds are allowed).')
        if self.settings["ImageGenerationPrice"] > 0:
            print(f'-- Image generation cost is {self.settings["ImageGenerationPrice"]} per image.')
        print('-- Learn more: https://platform.openai.com/docs/guides/images/usage\n')

    def load_image_generation_settings(self, deprecated=False):
        '''
        Load image generation settings from config file
        '''
        try:
            section = "ImageGeneration" if not deprecated else "OpenAI"
            settings = {}
            settings["ImageGenModel"] = self.config.get(section, "ImageGenModel")
            settings["ImageGenerationSize"] = self.config.get(section, "ImageGenerationSize")
            settings["ImageGenerationStyle"] = self.config.get(section, "ImageGenerationStyle")
            settings["ImageGenerationQuality"] = self.config.get(section, "ImageGenerationQuality")
            settings["ImageGenerationPrice"] = float(self.config.get(section, "ImageGenerationPrice"))
            settings["ImageRateLimitCount"] = int(self.config.get(section, "ImageRateLimitCount"))
            settings["ImageRateLimitTime"] = int(self.config.get(section, "ImageRateLimitTime"))
            self.end_user_id = False
            if self.config.has_section("OpenAI"):
                if self.config.has_option("OpenAI", "EndUserID"):
                    self.end_user_id = self.config.getboolean("OpenAI", "EndUserID")
            if self.config.has_section("ImageGeneration"):
                if self.config.has_option("ImageGeneration", "EndUserID"):
                    self.end_user_id = self.config.getboolean("ImageGeneration", "EndUserID")
            return settings
        except Exception as e:
            logger.error(f'Could not load image generation settings due: {e}')
            return None

    async def imagine(self, prompt, id=0, size="1024x1024", style="vivid", n=1, quality="standard", revision=False):
        '''
        Create image from text prompt
        Input:
            * prompt - text prompt
            * id - id of user
            * size - size of image (1024x1024, 1792x1024, or 1024x1792 for dall-e-3)
            * style - style of image (natural or vivid)
            * n - number of images to generate (only 1 for dall-e-3)
            * revision - if True, returns revised prompt
            * quality - quality of image (standard or hd - only for dall-e-3)
            
        See https://platform.openai.com/docs/api-reference/images/create for more details

        You can use the following keywords in prompt:
            * --natural - for natural style
            * --vivid - for vivid style
            * --sd - for standard quality
            * --hd - for hd quality
            * --horizontal - for horizontal image
            * --vertical - for vertical image
        '''
        # check if image generation is not rate limited
        if await self.image_rate_limit_check(id) == False:
            return None, f'Image generation is rate limited (only {self.settings["ImageRateLimitCount"]} images per {round(self.settings["ImageRateLimitTime"]/60)} minutes are allowed). Please try again later.'
        try:
            prompt = prompt.replace('—', '--')
            # extract arguments from prompt (if any)
            if '--natural' in prompt:
                style = 'natural'
                prompt = prompt.replace('--natural', '')
            if '--vivid' in prompt:
                style = 'vivid'
                prompt = prompt.replace('--vivid', '')
            if '--sd' in prompt:
                quality = 'standard'
                prompt = prompt.replace('--sd', '')
            if '--hd' in prompt:
                quality = 'hd'
                prompt = prompt.replace('--hd', '')
            if '--horizontal' in prompt:
                if self.settings["ImageGenModel"] == 'dall-e-3':
                    size = '1792x1024'
                prompt = prompt.replace('--horizontal', '')
            if '--vertical' in prompt:
                if self.settings["ImageGenModel"] == 'dall-e-3':
                    size = '1024x1792'
                prompt = prompt.replace('--vertical', '')
            prompt = prompt.strip()
            if prompt == '':
                return None, 'No text prompt was given. Please try again.'
            revised_prompt, b64_image = None, None
            user_id = hashlib.sha1(str(id).encode("utf-8")).hexdigest() if self.end_user_id else None
            response = await self.client.images.generate(
                        model=self.settings["ImageGenModel"],
                        prompt=prompt,
                        size=size,
                        quality=quality,
                        n=n,
                        response_format="b64_json",
                        style=style,
                        user=str(user_id)
                    )
            if response.data[0].b64_json:
                b64_image = response.data[0].b64_json
            if revision:
                try:
                    revised_prompt = response.data[0].revised_prompt
                except Exception as e:
                    logger.warning(f'Could not get revised prompt: {e}')
                    revised_prompt = None
            return b64_image, revised_prompt
        except self.openai.BadRequestError as e:
            logger.error('OpenAI BadRequestError: ' + str(e))
            if 'content_policy_violation' in str(e):
                return None, 'Your request was rejected because it may violate content policy. Please review it and try again.'
            return None, 'Your request was rejected. Please review it and try again.'
        except self.openai.RateLimitError as e:
            logger.error(f'OpenAI RateLimitError: {e}')
            return None, 'Service is getting rate limited. Please try again later.'
        except Exception as e:
            logger.exception('Could not imagine image from text')
            return None, None
        
    async def generate_image(self, prompt, image_orientation=None, image_style=None):
        '''
        Generate image from text prompt
        Input:
            * prompt - text prompt
            * orientation - orientation of image (landscape, portrait, default is None - square)
            * style - style of image (natural or vivid, default is None - vivid)
        '''
        try:
            logger.debug(f'Generating image from prompt: {prompt}, orientation: {image_orientation}, style: {image_style}')
            if prompt is None:
                return None, None
            size="1024x1024"
            style="vivid"
            if image_orientation is not None:
                if image_orientation == 'landscape':
                    size = '1792x1024'
                if image_orientation == 'portrait':
                    size = '1024x1792'
            if image_style is not None:
                if image_style == 'natural':
                    style = 'natural'
            b64_image, revised_prompt = await self.imagine(prompt, id='function', size=size, style=style, n=1, quality="standard", revision=True)
            return (b64_image, revised_prompt)
        except Exception as e:
            logger.exception('Could not generate image')
            return None

    async def image_rate_limit_check(self, id):
        '''
        Check if image generation is not rate limited
        Return True if not rate limited, False if rate limited
        '''
        try:
            if self.settings["ImageRateLimitCount"] <= 0 or self.settings["ImageRateLimitTime"] <= 0:
                return True
            if id not in self.image_rate_limit:
                self.image_rate_limit[id] = []
            # add current time to the list
            current_time = time.time()
            self.image_rate_limit[id].append(current_time)
            # remove old times
            self.image_rate_limit[id] = [t for t in self.image_rate_limit[id] if current_time - t < self.settings["ImageRateLimitTime"]]
            # check if count is not exceeded
            if len(self.image_rate_limit[id]) > self.settings["ImageRateLimitCount"]:
                return False
            return True
        except Exception as e:
            logger.error(f'Could not check image rate limit due to an error: {e}')
            return True



######## Stability Engine ########

class StabilityEngine:
    def __init__(self, api_key):
        '''
        Initialize Stability Engine
        '''
        import requests
        self.requests = requests
        import configparser
        self.config = configparser.SafeConfigParser({
            "ImageGenURL": "https://api.stability.ai/v2beta/stable-image/generate/core",
            "ImageGenerationRatio": "1:1",
            "ImageGenerationPrice": 0,
            "ImageRateLimitCount": 0,
            "ImageRateLimitTime": 0,
            "NegativePrompt": "None",
            "Seed": 0,
        })
        self.config.read('./data/.config')
        self.settings = self.load_image_generation_settings()
        if self.settings is None:
            raise Exception('Could not load image generation settings')

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "accept": "application/json",
        }

        print('Image generation via Stability Engine is enabled')
        print('-- Image generation is used to create images from text. It can be changed in the config file.')
        if self.settings["ImageRateLimitCount"] > 0 and self.settings["ImageRateLimitTime"] > 0:
            self.image_rate_limit = {}
            print(f'-- Image generation is rate limited (only {self.settings["ImageRateLimitCount"]} images per {self.settings["ImageRateLimitTime"]} seconds are allowed).')
        if self.settings["ImageGenerationPrice"] > 0:
            print(f'-- Image generation cost is {self.settings["ImageGenerationPrice"]} per image.')
        print('-- Learn more: https://platform.stability.ai/\n')

    def load_image_generation_settings(self):
        '''
        Load image generation settings from config file
        '''
        try:
            settings = {}
            settings["ImageGenURL"] = self.config.get("ImageGeneration", "ImageGenURL")
            settings["ImageGenerationSize"] = self.config.get("ImageGeneration", "ImageGenerationRatio")
            settings["ImageGenerationPrice"] = float(self.config.get("ImageGeneration", "ImageGenerationPrice"))
            settings["ImageRateLimitCount"] = int(self.config.get("ImageGeneration", "ImageRateLimitCount"))
            settings["ImageRateLimitTime"] = int(self.config.get("ImageGeneration", "ImageRateLimitTime"))
            settings["NegativePrompt"] = self.config.get("ImageGeneration", "NegativePrompt")
            if settings["NegativePrompt"] == "None":
                settings["NegativePrompt"] = None
            settings["Seed"] = int(self.config.get("ImageGeneration", "Seed"))
            settings["ImageGenerationStyle"] = "standard" # not supported by Stability Engine
            settings["ImageGenerationQuality"] = "standard" # not supported by Stability Engine
            return settings
        except Exception as e:
            logger.error(f'Could not load image generation settings due: {e}')
            return None

    async def imagine(self, prompt, id=0, ratio="1:1", negative_prompt=None, seed=0, output_format='jpeg', revision=False):
        '''
        Create image from text prompt
        Input:
            * prompt - text prompt
            * id - id of user
            * ratio - ratio of image (default: 1:1, also 16:9, 21:9, 2:3, 3:2, 4:5, 5:4, 9:16, 9:21 are supported)
            * negative_prompt - negative prompt to avoid (optional)
            * seed - seed for generation (0 for random seed)

        See https://platform.stability.ai/docs/api-reference for more details

        You can use the following keywords in prompt:
            * --ratio 16:9 - for 16:9 ratio (or any other supported ratio)
            * --negative <negative_prompt> - to avoid generating images similar to negative_prompt
            * --seed <seed> - to set seed for generation
            * --horizontal - for horizontal image (16:9 ratio)
            * --vertical - for vertical image (9:16 ratio)
        '''
        # check if image generation is not rate limited
        if await self.image_rate_limit_check(id) == False:
            return None, f'Image generation is rate limited (only {self.settings["ImageRateLimitCount"]} images per {round(self.settings["ImageRateLimitTime"]/60)} minutes are allowed). Please try again later.'
        try:
            if prompt is None:
                return None, 'No text prompt was given. Please try again.'
            if prompt == '':
                return None, 'Text prompt is empty. Please try again.'
            prompt = prompt.replace('—', '--')
            prompt = prompt.replace('  ', ' ')
            data = {}
            if self.settings["NegativePrompt"] is not None:
                data["negative_prompt"] = self.settings["NegativePrompt"]
            if self.settings["ImageGenerationSize"] is not None:
                data["aspect_ratio"] = self.settings["ImageGenerationSize"]
            if self.settings["Seed"] is not None:
                data["seed"] = self.settings["Seed"]

            if negative_prompt is not None:
                if "negative_prompt" in data:
                    data["negative_prompt"] += f"; {negative_prompt}"
                else:
                    data["negative_prompt"] = negative_prompt
            if seed > 0:
                data["seed"] = seed
            if ratio != "1:1":
                data["aspect_ratio"] = ratio

            # extract arguments from prompt (if any)
            if '--horizontal' in prompt:
                ratio = '16:9'
                prompt = prompt.replace('--horizontal', '')
            if '--vertical' in prompt:
                ratio = '9:16'
                prompt = prompt.replace('--vertical', '')
            if '--ratio' in prompt:
                ratio = prompt.split('--ratio')[1].strip()
                ratio = ratio.split()[0].strip()
                prompt = prompt.replace(f'--ratio {ratio}', '')
                data["aspect_ratio"] = ratio
            if '--negative' in prompt:
                negative_prompt = prompt.split('--negative')[1].strip()
                negative_prompt = negative_prompt.split()[0].strip()
                prompt = prompt.replace(f'--negative {negative_prompt}', '')
                data["negative_prompt"] += f"; {negative_prompt}" if "negative_prompt" in data else negative_prompt
            if '--seed' in prompt:
                seed = prompt.split('--seed')[1].strip()
                seed = seed.split()[0].strip()
                prompt = prompt.replace(f'--seed {seed}', '')
                data["seed"] = int(seed)

            data["prompt"] = prompt
            data["output_format"] = output_format

            response = self.requests.post(
                self.settings["ImageGenURL"],
                headers=self.headers,
                files={
                    "none": ''
                },
                data=data,
            )

            if response.status_code == 200:
                response_data = response.json()
                if "image" in response_data:
                    image = response_data["image"]
                    revised_prompt = f"Prompt: {prompt}. Seed: {response_data['seed']}. Finish Reason: {response_data['finish_reason']}" if revision else None
                    return image, revised_prompt
                else:
                    logger.error(f'Stability Error: {response.text}')
                    if "finish_reason" in response_data:
                        return None, f'Could not generate image. Finish Reason: {response_data["finish_reason"]}'
                    return None, f'Could not generate image. Please try again.'
            elif response.status_code == 400:
                logger.error(f'Stability BadRequestError: {response.text}')
                return None, 'Your request was rejected (BadRequest).'
            elif response.status_code == 403:
                logger.error(f'Stability ContentModerationError: {response.text}')
                return None, 'Your request was flagged by content moderation. Please review it and try again.'
            elif response.status_code == 500:
                logger.error(f'Stability InternalServerError: {response.text}')
                return None, 'Service is down. Please try again later.'
            else:
                logger.error(f'Stability Error: {response.text}')
                return None, 'Could not generate image. Please try again.'
        except Exception as e:
            logger.exception('Could not imagine image from text with Stability Engine')
            return None, None
        
    async def generate_image(self, prompt, image_orientation=None, image_style=None):
        '''
        Generate image from text prompt
        Input:
            * prompt - text prompt
            * orientation - orientation of image (landscape, portrait, default is None - square)
                if horizontal, use 16:9 ratio, if vertical, use 9:16 ratio
            * style - style of image (natural or vivid - NOT supported by Stability Engine)
        '''
        try:
            logger.debug(f'Generating image from prompt: {prompt}, orientation: {image_orientation}, style: {image_style}')
            if prompt is None:
                return None, None
            ratio="1:1"
            if image_orientation is not None:
                if image_orientation == 'landscape':
                    ratio = '16:9'
                if image_orientation == 'portrait':
                    ratio = '9:16'
            b64_image, revised_prompt = await self.imagine(prompt, id='function', ratio=ratio, negative_prompt=None, seed=0, output_format='jpeg')
            return (b64_image, revised_prompt)
        except Exception as e:
            logger.exception('Could not generate image with Stability Engine')
            return None

    async def image_rate_limit_check(self, id):
        '''
        Check if image generation is not rate limited
        Return True if not rate limited, False if rate limited
        '''
        try:
            if self.settings["ImageRateLimitCount"] <= 0 or self.settings["ImageRateLimitTime"] <= 0:
                return True
            if id not in self.image_rate_limit:
                self.image_rate_limit[id] = []
            # add current time to the list
            current_time = time.time()
            self.image_rate_limit[id].append(current_time)
            # remove old times
            self.image_rate_limit[id] = [t for t in self.image_rate_limit[id] if current_time - t < self.settings["ImageRateLimitTime"]]
            # check if count is not exceeded
            if len(self.image_rate_limit[id]) > self.settings["ImageRateLimitCount"]:
                return False
            return True
        except Exception as e:
            logger.error(f'Could not check image rate limit due to an error: {e}')
            return True
