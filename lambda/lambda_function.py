import json
import urllib.parse
import boto3
import os
import subprocess
import shlex
import shutil



print('Loading function')

s3 = boto3.client('s3')

SIGNED_URL_TIMEOUT = 60


def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))

    # Get the object from the event and show its content type
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    targetBucket = 'ept-output'
    
    try:
        response = {'Bucket': bucket, 'Key': key}
        
        s3_source_signed_url = s3.generate_presigned_url('get_object', 
        Params={'Bucket': bucket, 'Key': key}, ExpiresIn=SIGNED_URL_TIMEOUT)
        
        keyNoExtension = key.split(".",1)[0] 
        
        os.mkdir('/tmp/thumb')
        os.mkdir('/tmp/hls')

        ffmpeg_cmd_thumb = "/opt/bin/ffmpeg -i \"" + s3_source_signed_url + "\" -ss 00:00:05.000 -vframes 1 /tmp/thumb/output.png"
        ffmpeg_cmd_hls = "/opt/bin/ffmpeg -i \"" + s3_source_signed_url + "\" -codec: copy -start_number 0 -hls_time 10 -hls_list_size 0 -f hls /tmp/hls/" + keyNoExtension + ".m3u8"
        
        
        command1 = shlex.split(ffmpeg_cmd_thumb)
        command2 = shlex.split(ffmpeg_cmd_hls)
        p1 = subprocess.run(command1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p2 = subprocess.run(command2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        thumb =  open('/tmp/thumb/output.png', 'rb')
        resp = s3.put_object(Body=thumb, Bucket=targetBucket, Key='thumbs/' + keyNoExtension + ".png", ContentType='image/png')
        
        for filename in os.listdir('/tmp/hls/'):
            file = open('/tmp/hls/' + filename, 'rb')
            if (filename).endswith(".m3u8"):
                s3.put_object(Body=file, Bucket=targetBucket, Key= 'hls/' + keyNoExtension + '/' + filename, ContentType='application/x-mpegURL')
                continue
            if (filename).endswith(".ts"):
                s3.put_object(Body=file, Bucket=targetBucket, Key= 'hls/' + keyNoExtension + '/' + filename, ContentType='video/MP2T')
        
        # Cleanup incase of persistant cache
        shutil.rmtree('/tmp/thumb')
        shutil.rmtree('/tmp/hls')
        
        # s3.copy(response, 'ept-output', 'original/'key)
        # print("CONTENT TYPE: " + response['ContentType'])
        return {
            'statusCode': 200,
            'body': 'Processing of ' + key + ' successful.'
        }
    except Exception as e:
        print(e)
        print('Error getting object {} from bucket {}.'.format(key, bucket))
        # raise e