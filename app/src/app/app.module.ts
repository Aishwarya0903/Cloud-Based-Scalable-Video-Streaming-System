import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http'
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { ViewVideoComponent } from './view-video/view-video.component';
import { ApiService } from './service/api.service';

import { RouterModule } from '@angular/router';

import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatInputModule } from '@angular/material/input'

import { FlexLayoutModule } from '@angular/flex-layout';


import { VimeModule } from '@vime/angular';
import { AllVideosComponent } from './all-videos/all-videos.component';
import { UploadVideoComponent } from './upload-video/upload-video.component';
import { NotFoundComponent } from './not-found/not-found.component';
import { FormsModule } from '@angular/forms';
import { ReactiveFormsModule } from '@angular/forms';
import { ApiInterceptorService } from './service/api-interceptor.service';
import { LoginComponent } from './login/login.component';

@NgModule({
  declarations: [
    AppComponent,
    ViewVideoComponent,
    AllVideosComponent,
    UploadVideoComponent,
    NotFoundComponent,
    LoginComponent
  ],
  imports: [
    BrowserModule,
    AppRoutingModule,
    HttpClientModule,
    BrowserAnimationsModule,
    VimeModule,
    FormsModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatToolbarModule,
    FlexLayoutModule,
    MatCardModule,
    MatProgressBarModule,
    MatInputModule,
    RouterModule.forRoot([
      { path: '', component: AllVideosComponent },
      { path: 'video/:videoId', component: ViewVideoComponent },
      { path: 'upload', component: UploadVideoComponent },
      { path: 'login', component: LoginComponent},
      { path: '**', component: NotFoundComponent}
    ])
  ],
  providers: [
    ApiService,
    ApiInterceptorService
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
