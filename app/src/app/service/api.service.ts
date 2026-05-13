import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { catchError, map, Observable, of } from 'rxjs';
import { AuthService } from './auth.service';
import { environment } from 'src/environments/environment';

@Injectable({
  providedIn: 'root'
})

export class ApiService {

  apiUrl: string = environment.apiAddress;
  apiSuffix: string = '/api/v1'

  headers: HttpHeaders = new HttpHeaders().set('Content-Type', 'application/json');
  
  constructor(private http: HttpClient, private auth: AuthService) {}

  //Get Greeting
  getGreeting() {
    this.http.get<any>(`${this.apiUrl}/greeting`).subscribe(
      response => {
        console.log(response);
        return response;
      }
    );
  }

  getAllVideos(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}${this.apiSuffix}/video/`, 
    { headers: {'x-api-key': `${this.auth.getCurrentApiKey()}`}}).pipe(catchError(err => {
      return err;
    }))
  }

  getVideoDetails(id: String): Observable<any> {
    const apiRequestUrl = `${this.apiUrl}${this.apiSuffix}/video/${id}`;
    return this.http.get(apiRequestUrl,
      { headers: {'x-api-key': `${this.auth.getCurrentApiKey()}`}}).pipe(catchError(err => {
      return of([]);
    }));
  }

  uploadVideo(formData: FormData): Observable<any> {
    return this.http.post(`${this.apiUrl}${this.apiSuffix}/video/upload`, formData, {
      reportProgress: true,
      observe: 'events',
      headers: {'x-api-key': `${this.auth.getCurrentApiKey()}`}
    }).pipe(catchError(err => {
      return of([])
    }));
  }
}
