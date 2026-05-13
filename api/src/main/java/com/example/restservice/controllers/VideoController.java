package com.example.restservice.controllers;

import com.example.restservice.resources.UploadedVideo;
import com.example.restservice.resources.VideoWithURL;
import com.example.restservice.repositories.VideoRepository;
import com.example.restservice.resources.Video;
import com.example.restservice.services.StorageService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping(path = "api/v1/video")
public class VideoController {

    @Autowired
    private VideoRepository videoRepository;

    @Autowired
    private StorageService storageService;

    @CrossOrigin(origins = "*")
    @GetMapping("/")
    public List<VideoWithURL> getAllVideos() {
        List<VideoWithURL> allVideosWithURL = new ArrayList<VideoWithURL>();
        List<Video> allVideos = videoRepository.findAll();
        for (Video video : allVideos) {
            allVideosWithURL.add(new VideoWithURL(video));
        }
        return allVideosWithURL;
    }

    @CrossOrigin(origins = "*")
    @PutMapping("/")
    public Video addVideo() {
        Video video = new Video("Test", "Desc Test", "Uploader");
        videoRepository.saveAndFlush(video);
        return video;
    }

    @CrossOrigin(origins = "*")
    @GetMapping("/{id}")
    public List<VideoWithURL> getVideo(@PathVariable UUID id){
        List<VideoWithURL> videoWithURL = new ArrayList<VideoWithURL>();
        Optional<Video> result = videoRepository.findById(id);

        if(result.isPresent()){
            result.ifPresent(video -> {
                videoWithURL.add(new VideoWithURL(video));
            });
        }
        return videoWithURL;
    }

    @CrossOrigin(origins = "*")
    @PostMapping("/upload")
    public ResponseEntity<List<Video>> uploadVideo(
            @RequestParam(value = "file") MultipartFile file,
            @RequestParam(value = "videoTitle") String videoTitle,
            @RequestParam(value = "videoDesc") String videoDesc,
            @RequestParam(value = "uploadedBy") String uploadedBy
    ){
        try {
            UUID newVideoId = storageService.uploadFile(file);
            Video newVideo = new Video(newVideoId, videoTitle, videoDesc, uploadedBy);

            videoRepository.saveAndFlush(newVideo);

            List<Video> resp = new ArrayList<>();
            resp.add(newVideo);

            return ResponseEntity.ok(resp);
        } catch (Exception e){
            return ResponseEntity.internalServerError().build();
        }
    }
}
