export class Video {
    id: String;
    videoTitle: String;
    videoDesc?: String;
    uploadedBy?: String;
    views?: Number;
    uploadDate?: String;
    videoURL?: String;
    videoThumb?: String;

    constructor(id: string, videoTitle: string){
        this.id = id;
        this.videoTitle = videoTitle;
    }
}
