package com.example.restservice.resources;

public class VideoWithURL extends Video {

    final String CLOUDFRONT_URL = "https://d2tex1lxhqzov2.cloudfront.net";
    String videoURL;
    String videoThumb;

    public VideoWithURL(Video video) {
        super(video);
        this.videoURL = CLOUDFRONT_URL + "/hls/" + this.getId() + "/" + this.getId() + ".m3u8";
        this.videoThumb = CLOUDFRONT_URL + "/thumbs/" + this.getId() + ".png";
    }

    public String getVideoURL() {
        return videoURL;
    }

    public void setVideoURL(String videoURL) {
        this.videoURL = videoURL;
    }

    public String getVideoThumb() {
        return videoThumb;
    }

    public void setVideoThumb(String videoThumb) {
        this.videoThumb = videoThumb;
    }
}
