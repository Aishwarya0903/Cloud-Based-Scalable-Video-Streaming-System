import { Component, OnInit } from '@angular/core';
import { ApiService } from '../service/api.service';
import { Video } from '../video/video';

@Component({
  selector: 'app-all-videos',
  templateUrl: './all-videos.component.html',
  styleUrls: ['./all-videos.component.scss']
})
export class AllVideosComponent implements OnInit {

  constructor(private apiService: ApiService) { }

  allVideos: Array<Video> = [];
  allVideos2: Array<Video> = [];

  testData(): Video {
    const testVideoData = {
      "id": "138623c8-de19-4c68-b230-a9b8a0e8c616",
      "videoTitle": "Big Buck Bunny (HD)",
      "videoDesc": "The OG Big Buck Bunny Video",
      "uploadedBy": "Shane",
      "views": 0,
      "videoURL": "https://d2tex1lxhqzov2.cloudfront.net/hls/138623c8-de19-4c68-b230-a9b8a0e8c616/138623c8-de19-4c68-b230-a9b8a0e8c616.m3u8",
      "videoThumb": "https://d2tex1lxhqzov2.cloudfront.net/thumbs/138623c8-de19-4c68-b230-a9b8a0e8c616.png",
      "uploadDate": "2022-04-15T02:23:03.927172Z"
    }
    const video = new Video(testVideoData.id, testVideoData.videoTitle);
    video.videoDesc = testVideoData.videoDesc;
    video.uploadDate = testVideoData.uploadDate;
    video.uploadedBy = testVideoData.uploadedBy;
    video.views = testVideoData.views;
    video.videoURL = testVideoData.videoURL;
    video.videoThumb = testVideoData.videoThumb;

    return video;
  }

  ngOnInit(): void {
    this.allVideos.push(this.testData());

    const response = this.apiService.getAllVideos();
    response.subscribe(res => {
      this.allVideos2 = res;
      console.log(this.allVideos2);
    })
  }
}
