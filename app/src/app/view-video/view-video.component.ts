import { Component, OnInit } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import '@vime/core/themes/default.css';

import { ApiService } from '../service/api.service';
import { Video } from '../video/video';

@Component({
  selector: 'app-view-video',
  templateUrl: './view-video.component.html',
  styleUrls: ['./view-video.component.scss']
})
export class ViewVideoComponent implements OnInit {

  videoIdParam?: string | null;
  videoDetail?: Video;
  videoNotFound: Boolean = false;

  hlsConfig = {
    crossOrigin: ""
  }

  constructor(private apiService: ApiService, private route: ActivatedRoute) { 
  }

  ngOnInit(): void {
    this.route.paramMap.subscribe(params => {
      this.videoIdParam = params.get("videoId");
    })

    if(this.videoIdParam){
      const response = this.apiService.getVideoDetails(this.videoIdParam);
      response.subscribe(data => {
        if(data.length == 0){
          this.videoNotFound = true;
        }
        if(data.length > 0){
          this.videoDetail = new Video(data[0].videoId, data[0].videoTitle);
          this.videoDetail.videoDesc = data[0].videoDesc;
          this.videoDetail.videoURL = data[0].videoURL;
          this.videoDetail.uploadDate = data[0].uploadDate;
          this.videoDetail.videoThumb = data[0].videoThumb;
          this.videoDetail.views = data[0].views;
          console.log(data);
        }
      });
    }
  }
}
